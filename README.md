# 🐾 Mibish • Dokitti Sales Dashboard

A single, fully interactive Streamlit dashboard that reads **two kinds of data**
and auto-detects which one you gave it:

| Preset | Matches | What it shows |
|--------|---------|----------------|
| **Sales (salesperson)** | `Sales_Data_.csv` shape — *Party Name, Sales Person, City, State, monthly columns, Grand Total* | Monthly trend, sales by salesperson (click-to-drill), top states/cities/parties |
| **Product (category)** | `PAN_India` sheet shape — *Brand, Category, Product, monthly Qty + Sales* | Sales/Qty by category (click-to-drill), brand split, top products, trend |

Upload a CSV or XLSX and the app figures out the rest. Two sample files are bundled
so the app works the moment it's deployed.

---

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501

---

## Deploy for FREE (GitHub → Streamlit Community Cloud)

This is 100% free, no credit card, no server to manage.

### 1. Put the code on GitHub
Create a **new repository** (e.g. `dokitti-dashboard`) and upload these files,
keeping the folder structure:

```
dokitti-dashboard/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
└── sample_data/
    ├── sales_sample.csv
    └── product_sample.csv
```

Easiest way without the command line: on github.com click **Add file → Upload files**,
drag everything in, commit. (To keep the `.streamlit` folder, create the file
`.streamlit/config.toml` directly in GitHub's "create new file" box — type the path
with the slash and it makes the folder.)

If you prefer git:
```bash
git init
git add .
git commit -m "Dokitti dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/dokitti-dashboard.git
git push -u origin main
```

### 2. Deploy on Streamlit Community Cloud
1. Go to **https://share.streamlit.io** and sign in with the same GitHub account.
2. Click **Create app → Deploy a public app from GitHub**.
3. Pick your repo, branch `main`, main file `app.py`.
4. Click **Deploy**. First build takes ~2 minutes.

You'll get a public URL like `https://dokitti-dashboard.streamlit.app` you can
share with your team. Every time you push a new commit, it redeploys automatically.

> Free tier note: public apps are free and unlimited. If you need the app to be
> **private** (team-only), that's on Streamlit's paid tier — for a free private
> option instead, keep the repo private and run it internally, or use Hugging Face
> Spaces (also free) as an alternative host.

---

## How you feed data going forward

You said all future data will be CSV — perfect. Just keep the **column headers
identical** to the samples and the app keeps working. Two rules:

**Salesperson files** must keep these headers (month columns can be added/removed freely):
`Party Name, Sales Person, City, State, Apr, May, … , Grand Total`

**Product files** must keep:
`Brand, Category, SubCategory, Product Code, Product Name, April Qty, April Sales, May Qty, May Sales, …`

Numbers can stay in Indian format (`3,75,971.61`) — the app cleans them.
Salesperson name casing is normalised, so `AJAY SHAH` and `Ajay Shah` merge automatically.

To refresh the dashboard you can either **upload the new CSV in the app**, or
replace the file in `sample_data/` on GitHub and push.

---

## Features
- Auto-detect preset (with manual override in the sidebar)
- KPI cards, sidebar multiselect filters, month-range slider
- **Click a bar to drill down** (salesperson / category), with a clear button
- Trend, geography, brand, and top-N views
- Download the filtered data as CSV
- Teal / navy / gold theme
