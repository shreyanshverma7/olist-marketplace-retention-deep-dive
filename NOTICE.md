# Third-party data notice

The SQL, Python, and dashboard code in this repository is MIT-licensed (see [LICENSE](LICENSE)).

The underlying dataset is **not** authored by this project and carries its own terms:

- **Dataset**: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), published on Kaggle by Olist.
- **License**: CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike 4.0 International) — https://creativecommons.org/licenses/by-nc-sa/4.0/
- **Attribution**: "This is real commercial data provided by Olist, anonymised; product/reviewer references have been replaced with the names of Game of Thrones houses per the dataset publisher's own anonymisation process."

Practically, this means:

- **Attribution** — this project credits Olist and the Kaggle listing above as the data source (also noted in the README and in-app).
- **NonCommercial** — the data itself may not be used for commercial purposes. This repository is a non-commercial educational/portfolio project; the deployed dashboard is a free demo, not a commercial product.
- **ShareAlike** — any redistribution of the dataset (not this repo's original code) must carry the same license.

Neither the committed `database/olist.db` nor the raw CSVs are redistributed in a way that changes these terms — `data/raw/` is gitignored, and `database/olist.db` is a derived SQLite build of the same publicly-licensed data, built via [`database/build_olist_db.py`](database/build_olist_db.py) from the CSVs anyone can download directly from the Kaggle listing above.
