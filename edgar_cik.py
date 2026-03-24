import requests

HEADERS = {
    "User-Agent": "jhaley1212@gmail.com"
}

# 👇 THIS IS YOUR CIK LIST (easy to add more later)
CIKS = [
    "0001174610"
]

# Optional: filter for relevant ETF filings
ETF_FORMS = ["S-1", "N-1A", "485BPOS", "497"]

def fetch_filings_by_cik():
    all_filings = []

    for cik in CIKS:
        cik_padded = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"

        try:
            response = requests.get(url, headers=HEADERS)
            data = response.json()

            recent = data["filings"]["recent"]

            for i in range(len(recent["form"])):
                form = recent["form"][i]
                date = recent["filingDate"][i]
                accession = recent["accessionNumber"][i]
                company = data["name"]

                # Build filing link
                accession_clean = accession.replace("-", "")
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{accession}-index.htm"

                if True:
                    all_filings.append({
                        "company": company,
                        "form": form,
                        "date": date,
                        "link": filing_url,
                        "cik": cik
                    })

        except Exception as e:
            print(f"Error with CIK {cik}: {e}")

    return all_filings