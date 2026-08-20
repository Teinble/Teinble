# Private activity setup

The profile intentionally leaves activity metrics blank until private access is configured, so it never presents incomplete public-only numbers as your total work.

To include private repositories:

1. Create a fine-grained GitHub personal access token owned by `Teinble`.
2. Give it read-only access to **Metadata** and **Contents** for the repositories to count.
3. In the `Teinble/Teinble` repository, create an Actions secret named `PROFILE_TOKEN` containing that token.
4. Run the **Update profile statistics** workflow once from the Actions tab.

The SVG confirms how many private repositories are visible after syncing. `commits/day`, `active.days`, and the additions/deletions per day use authored commits on default branches over the trailing 365 days.

If the workflow says the token can see zero private repositories, edit or replace the PAT. For a fine-grained PAT, its resource owner must own the private repositories and those repositories must be selected. Organization-owned repositories may also require organization approval or SSO authorization.
