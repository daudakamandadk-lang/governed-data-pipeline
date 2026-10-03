# Public Reference Data

This directory contains **public reference datasets** used to test and develop the governed credit-risk pipeline.

These files are not employer/client data and are not intended to represent current Uganda credit behaviour. They are used as reproducible benchmark datasets for profiling, data-quality checks, ETL development, feature engineering and later model validation.

## Dataset availability

### Default of Credit Card Clients

- File: `default_credit_card_clients.csv`
- Repository status: empty placeholder (0 bytes); not a usable dataset. Obtain data from the official source before running extraction.
- Provider: UCI Machine Learning Repository
- Dataset ID: 350
- DOI: 10.24432/C55S3H
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Approximate size: 30,000 observations
- Intended use: default-risk analysis, DQ testing, feature engineering and model benchmarking
- Official source: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients

Attribution: Yeh, I. (2009). *Default of Credit Card Clients* [Dataset]. UCI Machine Learning Repository.

### South German Credit

- File: `south_german_credit.asc`
- Repository status: reference file present; inspect its whitespace-delimited format before loading.
- Provider: UCI Machine Learning Repository
- Dataset ID: 573
- DOI: 10.24432/C5QG88
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Approximate size: 1,000 observations
- Intended use: credit-risk classification, DQ testing and statistical benchmarking
- Official source: https://archive.ics.uci.edu/dataset/573/south+german+credit

Attribution: *South German Credit* [Dataset]. (2020). UCI Machine Learning Repository.

## Planned public reference sources

The wider credit-risk system also plans to use public or public-use information from sources such as:

- Uganda Bureau of Statistics / World Bank LSMS — Uganda National Panel Survey;
- Bank of Uganda — Bank Lending Survey and Monetary Policy Reports;
- World Bank — Global Findex;
- IMF — DataMapper macroeconomic indicators;
- HMDA loan-level public data;
- U.S. SBA 7(a)/504 public lending data;
- additional UCI credit/default datasets where licensing permits.

These sources are catalogued as reference/calibration inputs. Historical or foreign datasets must **not** be presented as current Uganda ground truth.

## Data-handling rule

Third-party data remains subject to its original licence and terms. The repository's MIT licence applies to the project code, not to third-party datasets.
