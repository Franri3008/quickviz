# Mock data for manual testing

Every number in these files is invented. Nothing here is real data. Each file has MOCK in its name.
Each file also carries the line "Source: mock data for testing, not real figures". The parser picks it
up as the starting source.

Upload a file in step 1. Type the sentence in step 2. Then try the chat edits in step 3.

| File | What it holds | Try typing in step 2 |
|---|---|---|
| `MOCK_ai_adoption_eu_countries_2025.csv` | Share of firms using AI in the 27 EU countries plus an EU27 row. Has ISO3 codes and country groups. A few values are missing as blank or `:` | Map of AI use by firms across EU countries |
| `MOCK_ai_vacancy_share_german_regions_wide.csv` | AI job ads as a share of all ads in the 16 German Länder. Years 2019 to 2025 are columns, so the parser turns them into Year and Value rows. Two cells are missing | Line chart of AI vacancy share by region over time |
| `MOCK_rd_spending_vs_ai_patents.csv` | R&D spending as a share of GDP and AI patents per million people, for EU countries plus US, Japan, South Korea and China | Scatter of R&D spending against AI patents, coloured by country group |
| `MOCK_energy_flows_two_sheets.xlsx` | Two sheets. "Electricity flows" holds exporter, importer and TWh. "Net balance" holds net imports per country, with negative values for net exporters | Sankey of electricity flows from exporter to importer |
| `MOCK_ai_patent_rank_countries_2015_2025.csv` | Rank of 12 EU countries by AI patent families each year, 2015 to 2025, plus the count | Bump chart of how country ranks changed over the years |
| `MOCK_survey_ai_use_by_sector_percent_text.csv` | Survey answers by sector. Uses AI now, plans to, or no plans. Shares are stored as text like "15.3%" | Stacked bar of survey answers by sector |
| `MOCK_occupation_by_ai_skill_heatmap.csv` | Share of job ads in 12 occupations that ask for each of 8 AI skills | Heatmap of AI skills by occupation |
| `MOCK_firm_size_distribution_2000_firms.csv` | 2,000 firms, one per row. Country, sector, employees, size class, productivity and whether they use AI | Histogram of productivity per worker |
| `MOCK_ai_use_gap_small_vs_large_firms.csv` | AI use by small and by large firms in each EU country, plus EU27 | Dot range of the gap between small and large firms by country |
| `MOCK_energy_imports_wide.xlsx` | Energy imports by source, one row per year 2001 to 2025, a column per source and an empty TOTAL column. Sources differ a lot in size. Under the table sits a near-empty block of years, which the parser leaves out | Stacked bar of energy imports by source per year |
| `MOCK_ai_venture_capital_by_technology_semicolon.csv` | Quarterly venture capital in EUR million for 6 AI technologies, 2021-Q1 to 2025-Q4. Semicolon file with decimal commas | Stacked area of venture capital by technology over time |

Other kinds to try on the same files.
Bar and treemap fit the adoption file.
Donut fits the venture capital file, with one technology per slice.
The "Net balance" sheet of the energy workbook gives a map with negative values.
The German regions file gives a region map if you filter to 2025.

## Chat edits to try in step 3

- On the adoption bar chart: "Highlight Belgium and sort from high to low"
- On the vacancy line chart: "Keep only Berlin, Bayern and Sachsen from 2021 onwards"
- On the stacked bar: "Show only Uses AI now and make it a bar chart sorted by value"
