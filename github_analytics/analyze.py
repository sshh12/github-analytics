import plotly.express as px
import pandas as pd
import collections
import github
import os
import re


PRMeta = collections.namedtuple("PRMeta", "reviewers review_passes hours_to_merge total_changes")


def _parse_pr_title_verb(pr):
    verb = re.sub(r"\[[\w\-& ]+\] ", "", pr.title).lower().split(" ")[0]
    verb = verb.replace(":", "")
    if verb in ["adding", "added"]:
        verb = "add"
    if verb in ["fixing"]:
        verb = "fix"
    if verb in ["removing"]:
        verb = "remove"
    return verb


def _cnt_pr_passes(reviews, commits, author):
    events = [("review", review.submitted_at) for review in reviews if review.user != author] + [
        ("commit", commit.commit.author.date) for commit in commits
    ]
    events.sort(key=lambda e: e[1])
    last = "commit"
    passes = 0
    for evt_type, _ in events:
        if last == "commit" and evt_type == "review":
            passes += 1
        last = evt_type
    return passes


def _get_pr_meta_info(pr):
    requested_users = list(pr.get_review_requests()[0])
    historical_reviews = list(pr.get_reviews())
    reviewers = set(requested_users + [review.user for review in historical_reviews]) - set([pr.user])
    review_passes = _cnt_pr_passes(historical_reviews, pr.get_commits(), pr.user)
    if pr.merged_at:
        hours_to_merge = (pr.merged_at - pr.created_at).total_seconds() / (60 * 60)
    else:
        hours_to_merge = None
    total_changes = pr.additions + pr.deletions
    return PRMeta(reviewers, review_passes, hours_to_merge, total_changes)


class PRAnalyzer:
    def __init__(self, repo, org, org_team, github_api_token=None):
        if github_api_token is None:
            github_api_token = os.environ["GITHUB_API_TOKEN"]
        self.github = github.Github(github_api_token)
        self.repo_name = repo
        self.org_name = org
        self.org_team_name = org_team
        self.repo = None
        self.org = None
        self.team = None
        self.team_users = None
        self.prs = None
        self.valid_prs = None
        self.pr_to_meta = {}

    def download(self):
        self.repo = self.github.get_repo(self.repo_name)
        self.org = self.github.get_organization(self.org_name)
        self.team = [team for team in self.org.get_teams() if team.name == self.org_team_name][0]
        self.team_users = list(self.team.get_members())
        self.prs = list(self.repo.get_pulls(state="all"))
        self.valid_prs = [pr for pr in self.prs if pr.user in self.team_users and pr.base.label.endswith(":main")]
        for pr in self.valid_prs:
            self.pr_to_meta[pr] = _get_pr_meta_info(pr)

    def get_summary_stats(self):
        pr_rows = []
        for pr, meta in self.pr_to_meta.items():
            if not pr.merged_at:
                continue
            pr_rows.append([meta.review_passes, meta.hours_to_merge, meta.total_changes, len(meta.reviewers)])
        pr_df = pd.DataFrame(pr_rows, columns=["review_passes", "hours_to_merge", "total_changes", "num_reviewers"])
        summary_rows = []
        for col in pr_df.columns:
            summary_rows.append(
                [
                    col,
                    pr_df[col].mean(),
                    pr_df[col].median(),
                    pr_df[col].quantile(0.9),
                    pr_df[col].min(),
                    pr_df[col].max(),
                ]
            )
        summary_df = pd.DataFrame(summary_rows, columns=["name", "mean", "median", "p90", "min", "max"]).set_index(
            "name"
        )
        return summary_df

    def plot_hours_to_merge_histogram(self, max_hours=120, bins=40):
        hours_to_merge = [min(max_hours, self.pr_to_meta[pr].hours_to_merge) for pr in self.valid_prs if pr.merged_at]
        df = pd.DataFrame({"hours_to_merge": hours_to_merge})
        fig = px.histogram(
            df,
            x="hours_to_merge",
            nbins=bins,
            title="PR Hours To Merge ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_hours_to_merge_by_author_boxplot(self, max_hours=120):
        hours_to_merge = [min(max_hours, self.pr_to_meta[pr].hours_to_merge) for pr in self.valid_prs if pr.merged_at]
        usernames = [pr.user.login for pr in self.valid_prs if pr.merged_at]
        df = pd.DataFrame({"hours_to_merge": hours_to_merge, "user": usernames})
        fig = px.box(
            df,
            x="hours_to_merge",
            color="user",
            title="PR Hours To Merge By Author ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_reviewer_proportion_of_prs_pie(self):
        pr_cnt_by_user = collections.defaultdict(int)
        for _, meta in self.pr_to_meta.items():
            for reviewer in meta.reviewers:
                if reviewer not in self.team_users:
                    continue
                pr_cnt_by_user[reviewer.login] += 1
        df = pd.DataFrame(pr_cnt_by_user.items(), columns=["reviewer", "prs"])
        fig = px.pie(
            df,
            values="prs",
            names="reviewer",
            title="PRs Assigned To Reviewers ({})".format(self.org_team_name),
        )
        return fig, df

    def _get_changes_by_authors_and_reviewers(self):
        pr_changes_by_author = collections.defaultdict(int)
        for pr, meta in self.pr_to_meta.items():
            pr_changes_by_author[pr.user.login] += meta.total_changes
        pr_changes_by_reviewer = collections.defaultdict(int)
        for _, meta in self.pr_to_meta.items():
            for reviewer in meta.reviewers:
                if reviewer not in self.team_users:
                    continue
                pr_changes_by_reviewer[reviewer.login] += meta.total_changes
        return pr_changes_by_author, pr_changes_by_reviewer

    def plot_reviewer_proportion_of_changes_pie(self):
        _, pr_changes_by_reviewer = self._get_changes_by_authors_and_reviewers()
        df = pd.DataFrame(pr_changes_by_reviewer.items(), columns=["reviewer", "changes"])
        fig = px.pie(
            df,
            values="changes",
            names="reviewer",
            title="PR Changes Assigned To Reviewers ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_author_proportion_of_changes_pie(self):
        pr_changes_by_author, _ = self._get_changes_by_authors_and_reviewers()
        df = pd.DataFrame(pr_changes_by_author.items(), columns=["author", "changes"])
        fig = px.pie(
            df,
            values="changes",
            names="author",
            title="PR Changes By Author ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_changes_reviewed_vs_created_scatter(self):
        pr_changes_by_author, pr_changes_by_reviewer = self._get_changes_by_authors_and_reviewers()
        df_author = pd.DataFrame(pr_changes_by_author.items(), columns=["user", "changes_created"]).set_index("user")
        df_reviewer = pd.DataFrame(pr_changes_by_reviewer.items(), columns=["user", "changes_reviewed"]).set_index(
            "user"
        )
        df = df_author.join(df_reviewer).reset_index()
        mx_val = max(df.changes_reviewed.max(), df.changes_created.max())
        fig = px.scatter(
            df,
            x="changes_reviewed",
            y="changes_created",
            color="user",
            title="PR Changes Reviewed vs Created ({})".format(self.org_team_name),
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=mx_val, y1=mx_val)
        return fig, df

    def plot_pr_verb_pie(self, n=10):
        cnts_of_verbs = collections.Counter([_parse_pr_title_verb(pr) for pr in self.valid_prs])
        df = pd.DataFrame(cnts_of_verbs.most_common(n), columns=["word", "cnt"])
        fig = px.pie(
            df,
            values="cnt",
            names="word",
            title="PR Title Verbs ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_hours_to_merge_user_heatmap(self, max_hours=120):
        author_reviewer_hours_to_merge = collections.defaultdict(list)
        for pr, meta in self.pr_to_meta.items():
            if not pr.merged_at:
                continue
            for reviewer in meta.reviewers:
                if reviewer not in self.team_users:
                    continue
                author_reviewer_hours_to_merge[(pr.user.login, reviewer.login)].append(
                    min(max_hours, meta.hours_to_merge)
                )
        usernames = sorted([user.login for user in self.team_users])
        heatmap = [[0] * len(usernames) for _ in range(len(usernames))]
        for (author, reviewer), hours_to_merge in author_reviewer_hours_to_merge.items():
            hours_to_merge_mean = sum(hours_to_merge) / len(hours_to_merge)
            heatmap[usernames[::-1].index(author)][usernames.index(reviewer)] = hours_to_merge_mean
        df = pd.DataFrame(heatmap, index=usernames[::-1], columns=usernames)
        fig = px.imshow(
            heatmap,
            x=usernames,
            y=usernames[::-1],
            labels=dict(x="Reviewer", y="Author", color="Mean Hours To Merge"),
            title="PR Hours To Merge Heatmap ({})".format(self.org_team_name),
        )
        return fig, df

    def plot_changes_vs_hours_to_merge_scatter(self, max_hours=500):
        hours_to_merge = [min(max_hours, self.pr_to_meta[pr].hours_to_merge) for pr in self.valid_prs if pr.merged_at]
        changes = [self.pr_to_meta[pr].total_changes for pr in self.valid_prs if pr.merged_at]
        users = [pr.user.login for pr in self.valid_prs if pr.merged_at]
        df = pd.DataFrame({"hours_to_merge": hours_to_merge, "total_changes": changes, "author": users})
        fig = px.scatter(
            df,
            y="hours_to_merge",
            x="total_changes",
            color="author",
            title="PR Hours To Merge vs Total Changes ({})".format(self.org_team_name),
        )
        return fig

    def plot_review_passes_by_author_boxplot(self):
        passes = [self.pr_to_meta[pr].review_passes for pr in self.valid_prs if pr.merged_at]
        users = [pr.user.login for pr in self.valid_prs if pr.merged_at]
        df = pd.DataFrame({"review_passes": passes, "author": users})
        fig = px.box(
            df, x="review_passes", color="author", title="Review Passes By Author ({})".format(self.org_team_name)
        )
        return fig, df

    def plot_review_passes_by_reviewer_boxplot(self):
        passes = []
        users = []
        for pr, meta in self.pr_to_meta.items():
            if not pr.merged_at:
                continue
            for reviewer in meta.reviewers:
                if reviewer not in self.team_users:
                    continue
                passes.append(meta.review_passes)
                users.append(reviewer.login)
        passes = [self.pr_to_meta[pr].review_passes for pr in self.valid_prs if pr.merged_at]
        users = [pr.user.login for pr in self.valid_prs if pr.merged_at]
        df = pd.DataFrame({"review_passes": passes, "reviewer": users})
        fig = px.box(
            df,
            x="review_passes",
            color="reviewer",
            title="PR Review Passes By Reviewer ({})".format(self.org_team_name),
        )
        return fig, df
