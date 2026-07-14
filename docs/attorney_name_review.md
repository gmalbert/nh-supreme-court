# Attorney-name review queue

This is a review queue, not a list of confirmed errors. It is generated from the official oral-argument roster and excludes names already covered by `data/attorney_name_map.json`.

## How to give feedback

Reply with a row ID and one instruction. For example:

- `N-004 → MAP TO: Brian J.S. Cullen`
- `N-009 → SPLIT: Alice A. Lawyer; Bob B. Lawyer`
- `N-015 → REMOVE (organization, not counsel)`
- `N-021 → KEEP (this is a real distinct attorney)`

I will convert only your confirmed decisions into the name map or a narrow roster correction, then rebuild the statistics.

## Remove — non-attorney entries

| ID | Roster text | Docket(s) | Why |
|---|---|---|---|
| N-001 | American Institute | [`2024-0138`](../case-explorer?case=2024-0138) | Organization or party name was parsed as an attorney |
| N-002 | Bureau of Securities Regulation | [`2014-0650`](../case-explorer?case=2014-0650) | Organization or party name was parsed as an attorney |
| N-003 | Business Trust | [`2015-0382`](../case-explorer?case=2015-0382) | Organization or party name was parsed as an attorney |
| N-004 | Community Services | [`2015-0748`](../case-explorer?case=2015-0748) | Organization or party name was parsed as an attorney |
| N-005 | Condominium Association | [`2023-0142`](../case-explorer?case=2023-0142) | Organization or party name was parsed as an attorney |
| N-006 | Environmental Services | [`2017-0142`](../case-explorer?case=2017-0142) | Organization or party name was parsed as an attorney |
| N-007 | Farmington School District | [`2015-0032`](../case-explorer?case=2015-0032) | Organization or party name was parsed as an attorney |
| N-008 | Hampshire Association | [`2023-0357`](../case-explorer?case=2023-0357) | Organization or party name was parsed as an attorney |
| N-009 | Hampshire Commission | [`2023-0319`](../case-explorer?case=2023-0319) | Organization or party name was parsed as an attorney |
| N-010 | Hampshire Division | [`2019-0535`](../case-explorer?case=2019-0535), [`2021-0563`](../case-explorer?case=2021-0563) | Organization or party name was parsed as an attorney |
| N-011 | Hampshire Liquor Commission | [`2014-0583`](../case-explorer?case=2014-0583), [`2016-0594`](../case-explorer?case=2016-0594) | Organization or party name was parsed as an attorney |
| N-012 | Hampshire Municipal Association | [`2022-0237`](../case-explorer?case=2022-0237) | Organization or party name was parsed as an attorney |
| N-013 | Hampshire Retirement System | [`2019-0654`](../case-explorer?case=2019-0654) | Organization or party name was parsed as an attorney |
| N-014 | Health Services Planning | [`2014-0674`](../case-explorer?case=2014-0674), [`2015-0301`](../case-explorer?case=2015-0301) | Organization or party name was parsed as an attorney |
| N-015 | Human Services | [`2015-0071`](../case-explorer?case=2015-0071) | Organization or party name was parsed as an attorney |
| N-016 | Human Services Administrative Appeals Unit | [`2015-0395`](../case-explorer?case=2015-0395), [`2015-0748`](../case-explorer?case=2015-0748) | Organization or party name was parsed as an attorney |
| N-017 | Human Services, Administrative Appeals Unit | [`2023-0488`](../case-explorer?case=2023-0488), [`2025-0064`](../case-explorer?case=2025-0064) | Organization or party name was parsed as an attorney |
| N-018 | Land Appeals | [`2018-0217`](../case-explorer?case=2018-0217), [`2019-0061`](../case-explorer?case=2019-0061), [`2021-0392`](../case-explorer?case=2021-0392), [`2022-0525`](../case-explorer?case=2022-0525) | Organization or party name was parsed as an attorney |
| N-019 | Manchester School District | [`2016-0582`](../case-explorer?case=2016-0582) | Organization or party name was parsed as an attorney |
| N-020 | Minority Leader | [`2022-0184`](../case-explorer?case=2022-0184) | Organization or party name was parsed as an attorney |
| N-021 | New Hampshire Center | [`2019-0279`](../case-explorer?case=2019-0279) | Organization or party name was parsed as an attorney |
| N-022 | New Hampshire Commission for Human Rights | [`2023-0319`](../case-explorer?case=2023-0319) | Organization or party name was parsed as an attorney |
| N-023 | New Hampshire Governor’s Office | [`2020-0536`](../case-explorer?case=2020-0536) | Organization or party name was parsed as an attorney |
| N-024 | New Hampshire Liquor Commission | [`2024-0531`](../case-explorer?case=2024-0531) | Organization or party name was parsed as an attorney |
| N-025 | New Hampshire Lottery Commission | [`2024-0722`](../case-explorer?case=2024-0722), [`2024-0722-2024-0723`](../case-explorer?case=2024-0722-2024-0723) | Organization or party name was parsed as an attorney |
| N-026 | New Hampshire Professional Conduct Committee | [`2024-0005`](../case-explorer?case=2024-0005) | Organization or party name was parsed as an attorney |
| N-027 | New Hampshire Public Utilities Commission | [`2022-0146`](../case-explorer?case=2022-0146) | Organization or party name was parsed as an attorney |
| N-028 | New Hampshire Retirement System | [`2023-0471`](../case-explorer?case=2023-0471), [`2025-0015`](../case-explorer?case=2025-0015) | Organization or party name was parsed as an attorney |
| N-029 | Police Supervisors’ Association | [`2014-0801`](../case-explorer?case=2014-0801) | Organization or party name was parsed as an attorney |
| N-030 | Portsmouth Regional Hospital | [`2023-0156`](../case-explorer?case=2023-0156) | Organization or party name was parsed as an attorney |
| N-031 | Public Protection Fund | [`2016-0427`](../case-explorer?case=2016-0427) | Organization or party name was parsed as an attorney |
| N-032 | Public Protection Fund Committee | [`2016-0427`](../case-explorer?case=2016-0427) | Organization or party name was parsed as an attorney |
| N-033 | Public Utilities Commission | [`2017-0007`](../case-explorer?case=2017-0007) | Organization or party name was parsed as an attorney |
| N-034 | School District | [`2015-0030`](../case-explorer?case=2015-0030), [`2016-0558`](../case-explorer?case=2016-0558) | Organization or party name was parsed as an attorney |
| N-035 | Site Evaluation Committee | [`2018-0468`](../case-explorer?case=2018-0468), [`2019-0277`](../case-explorer?case=2019-0277) | Organization or party name was parsed as an attorney |
| N-036 | Wentworth-Douglass Hospital | [`2024-0005`](../case-explorer?case=2024-0005) | Organization or party name was parsed as an attorney |
| N-037 | Western Asbestos Settlement Trust | [`2016-0569`](../case-explorer?case=2016-0569) | Organization or party name was parsed as an attorney |

## Split — multiple attorneys merged into one field

| ID | Merged roster text | Docket(s) | What I will do |
|---|---|---|---|
| N-038 | Aaron J. Curtis, Colin F. McGrath | [`2020-0454`](../case-explorer?case=2020-0454) | Split into separately named attorneys after source verification |
| N-039 | Cordell A. Johnston, Stephen C. Buckley | [`2019-0206`](../case-explorer?case=2019-0206) | Split into separately named attorneys after source verification |
| N-040 | David Himelfarb, John M. Allen | [`2025-0140`](../case-explorer?case=2025-0140) | Split into separately named attorneys after source verification |
| N-041 | Gilles R. Bissonnette, Henry R. Klementowicz | [`2019-0057`](../case-explorer?case=2019-0057) | Split into separately named attorneys after source verification |
| N-042 | Jane E. Young, Daniel E. Will | [`2019-0654`](../case-explorer?case=2019-0654) | Split into separately named attorneys after source verification |
| N-043 | John Houlihan, Steven T. Whitmer | [`2016-0569`](../case-explorer?case=2016-0569) | Split into separately named attorneys after source verification |

## Map — attorney-name variants

| ID | Roster name | Suggested canonical name | Docket(s) |
|---|---|---|---|
| N-044 | Alexander Scott | Alexander W. Scott | [`2019-0654`](../case-explorer?case=2019-0654) |
| N-045 | Brain J.S. Cullen | Brian J.S. Cullen | [`2014-0315`](../case-explorer?case=2014-0315) |
| N-046 | Brendan Avery O’Donnell | Brendan A. O’Donnell | [`2020-0538`](../case-explorer?case=2020-0538) |
| N-047 | Brian J. S. Cullen | Brian J.S. Cullen | [`2018-0624`](../case-explorer?case=2018-0624) |
| N-048 | Callan Sullivan | Callan E. Sullivan | [`2024-0121`](../case-explorer?case=2024-0121), [`2024-0138`](../case-explorer?case=2024-0138) |
| N-049 | Carolyn Cole | Carolyn K. Cole | [`2016-0304`](../case-explorer?case=2016-0304) |
| N-050 | Charles Bauer | Charles P. Bauer | [`2020-0216`](../case-explorer?case=2020-0216) |
| N-051 | Christina Wilson | Christina M. Wilson | [`2021-0053`](../case-explorer?case=2021-0053) |
| N-052 | Christopher H. M. Carter | Christopher H.M. Carter | [`2015-0692`](../case-explorer?case=2015-0692) |
| N-053 | Craig McMahon | Craig T. McMahon | [`2022-0208`](../case-explorer?case=2022-0208) |
| N-054 | Danielle Pacik | Danielle L. Pacik | [`2024-0224`](../case-explorer?case=2024-0224) |
| N-055 | Doreen Connor | Doreen F. Connor | [`2022-0155`](../case-explorer?case=2022-0155) |
| N-056 | Francis C. Fredericks | Francis C. Fredericks, Jr. | [`2015-0499`](../case-explorer?case=2015-0499) |
| N-057 | Garrett Harris | Garrett J. Harris | [`2021-0585`](../case-explorer?case=2021-0585) |
| N-058 | Gary Apfel | Gary N. Apfel | [`2018-0328`](../case-explorer?case=2018-0328) |
| N-059 | Gary Snyder | Gary J. Snyder | [`2017-0530`](../case-explorer?case=2017-0530), [`2018-0296`](../case-explorer?case=2018-0296), [`2021-0027`](../case-explorer?case=2021-0027) |
| N-060 | Heather Neville | Heather D. Neville | [`2017-0530`](../case-explorer?case=2017-0530) |
| N-061 | Jacob Marvelley | Jacob J. B. Marvelley | [`2015-0583`](../case-explorer?case=2015-0583), [`2023-0278`](../case-explorer?case=2023-0278) |
| N-062 | James F. LaFrance | James F. Lafrance | [`2022-0222`](../case-explorer?case=2022-0222) |
| N-063 | James W. Kennedy | James W. Kennedy, III | [`2015-0510`](../case-explorer?case=2015-0510) |
| N-064 | John J. McCormack, IV | John J. McCormack | [`2013-0653`](../case-explorer?case=2013-0653) |
| N-065 | John M. Sullivan | John F. Sullivan | [`2019-0120`](../case-explorer?case=2019-0120) |
| N-066 | John Yanchunis | John A. Yanchunis | [`2022-0224`](../case-explorer?case=2022-0224) |
| N-067 | Joseph H. Driscoll IV | Joseph H. Driscoll, IV | [`2023-0687`](../case-explorer?case=2023-0687) |
| N-068 | Kevin Truland | Kevin M. Truland | [`2014-0285`](../case-explorer?case=2014-0285) |
| N-069 | Laura A. Spector- Morgan | Laura A. Spector-Morgan | [`2014-0203`](../case-explorer?case=2014-0203), [`2015-0671`](../case-explorer?case=2015-0671), [`2016-0304`](../case-explorer?case=2016-0304) |
| N-070 | Laura E.B. Lombardi | Laura E. B. Lombardi | [`2017-0403`](../case-explorer?case=2017-0403) |
| N-071 | Laura Spector- Morgan | Laura Spector-Morgan | [`2015-0264`](../case-explorer?case=2015-0264) |
| N-072 | Lisa Snow Wade | Lisa K. Snow Wade | [`2023-0436`](../case-explorer?case=2023-0436), [`2024-0720`](../case-explorer?case=2024-0720), [`2025-0178`](../case-explorer?case=2025-0178) |
| N-073 | Mark Sisti | Mark L. Sisti | [`2016-0535`](../case-explorer?case=2016-0535) |
| N-074 | Mary Beth Sweeney | Mary Beth L. Sweeney | [`2024-0155`](../case-explorer?case=2024-0155) |
| N-075 | Matthew Broadhead | Matthew T. Broadhead | [`2022-0237`](../case-explorer?case=2022-0237) |
| N-076 | Matthew McNicoll | Matthew T. McNicoll | [`2023-0166`](../case-explorer?case=2023-0166), [`2024-0496`](../case-explorer?case=2024-0496) |
| N-077 | Matthew Serge | Matthew R. Serge | [`2022-0592`](../case-explorer?case=2022-0592) |
| N-078 | Megan Douglass | Megan E. Douglass | [`2016-0398`](../case-explorer?case=2016-0398) |
| N-079 | Michael Eaton | Michael G. Eaton | [`2019-0057`](../case-explorer?case=2019-0057) |
| N-080 | Nathan W. Kenison- Marvin | Nathan W. Kenison-Marvin | [`2022-0208`](../case-explorer?case=2022-0208) |
| N-081 | R. Peter DeCato | R. Peter Decato | [`2016-0657`](../case-explorer?case=2016-0657) |
| N-082 | Richard C. Guerriero, Jr. | Richard C. Guerriero | [`2019-0200`](../case-explorer?case=2019-0200) |
| N-083 | Richard Guerriero | Richard C. Guerriero | [`2019-0022`](../case-explorer?case=2019-0022) |
| N-084 | Robert Baldridge | Robert L. Baldridge | [`2023-0408`](../case-explorer?case=2023-0408) |
| N-085 | Sam Gonyea | Sam M. Gonyea | [`2023-0604`](../case-explorer?case=2023-0604) |
| N-086 | Scott Chase | Scott D. Chase | [`2016-0698`](../case-explorer?case=2016-0698) |
| N-087 | Sean Locke | Sean R. Locke | [`2023-0663`](../case-explorer?case=2023-0663) |
| N-088 | Sharon Rondeau | Sharon J. Rondeau | [`2018-0244`](../case-explorer?case=2018-0244), [`2020-0201`](../case-explorer?case=2020-0201) |
| N-089 | Silas Little | Silas Little, III | [`2015-0250`](../case-explorer?case=2015-0250) |
| N-090 | Theodore E. Tsekerides, all pro hac vice | Theodore E. Tsekerides | [`2020-0454`](../case-explorer?case=2020-0454) |
| N-091 | Theodore Lothstein | Theodore M. Lothstein | [`2022-0503`](../case-explorer?case=2022-0503) |
| N-092 | William Aivalikles | William E. Aivalikles | [`2021-0448`](../case-explorer?case=2021-0448), [`2023-0521`](../case-explorer?case=2023-0521) |
| N-093 | Zachary Lee Higham | Zachary L. Higham | [`2019-0371`](../case-explorer?case=2019-0371) |


Generated from 1,011 distinct raw roster names; 93 entries need review.
