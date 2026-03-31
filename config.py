HEADERS = {
    "User-Agent": "ETF Dashboard (jhaley1212@gmail.com)"
}

CIK_ENTRIES = [
    ("0001761055", "BlackRock ETF Trust"),
    ("0001804196", "BlackRock ETF Trust II"),
    ("0001100663", "iShares Trust"),
    ("0001414509", "iShares U.S. ETF Trust"),
    ("0001337567", "iShares Gold Trust"),
    ("0000932476", "Vanguard Fixed Income Securities Funds"),
    ("0000882184", "Vanguard Whitehall Funds"),
    ("0000932477", "SPDR Series Trust"),
    ("0001064642", "SPDR Series Trust"),
    ("0001350487", "WisdomTree Trust"),
    ("0001364742", "SPDR MSCI World StrategicFactors ETF Trust"),
    ("0001400683", "SPDR ICE Preferred Securities ETF Trust"),
    ("0001454967", "SPDR DoubleLine Total Return Tactical ETF"),
    ("0001333493", "Invesco Actively Managed Exchange-Traded Fund Trust"),
    ("0001592900", "EA Series Trust"),
    ("0001424958", "Direxion Shares ETF Trust"),
    ("0001452937", "Exchange Traded Concepts Trust"),
    ("0001452938", "Invesco DB Commodity Index Tracking Fund"),
    ("0001064641", "Select Sector SPDR Trust"),
    ("0001454889", "Schwab Strategic Trust"),
    ("0001454888", "Schwab Capital Trust"),
    ("0001109241", "JPMorgan Trust I"),
    ("0001587982", "Investment Managers Series Trust II"),
    ("0001090372", "First Trust Exchange-Traded Fund"),
    ("0001090374", "First Trust Exchange-Traded Fund III"),
    ("0001279890", "First Trust Exchange-Traded AlphaDEX Fund"),
    ("0001320414", "First Trust Exchange-Traded Fund IV"),
    ("0001137360", "VanEck ETF Trust"),
    ("0000863064", "VanEck Vectors ETF Trust"),
    ("0001015965", "VanEck VIP Trust"),
    ("0000315066", "Fidelity Covington Trust"),
    ("0000036405", "Vanguard Index Funds"),
    ("0000819118", "Fidelity Concord Street Trust"),
    ("0000051931", "American Funds Insurance Series"),
    ("0001582983", "Capital Group Exchange-Traded Fund Trust"),
    ("0001471855", "American Century ETF Trust"),
    ("0000354908", "American Century Investment Trust"),
    ("0000804239", "American Century Mutual Funds, Inc."),
    ("0000914863", "American Century Strategic Asset Allocations, Inc."),
    ("0001174610", "ProShares Trust"),
    ("0001318342", "Investment Managers Series Trust"),
    ("0001308648", "ProShares Trust III"),
    ("0000899140", "ProFunds Trust"),
    ("0001378992", "WisdomTree Trust II"),
    ("0001414508", "WisdomTree Trust III"),
    ("0001633061", "Amplify ETF Trust"),
    ("0001432353", "Global X Funds"),
    ("0001432354", "Global X Funds II"),
    ("0000886982", "Goldman Sachs ETF Trust"),
    ("0001582981", "Goldman Sachs ActiveBeta ETF Trust"),
    ("0001318343", "Direxion Shares ETF Trust II"),
    ("0001308649", "Direxion Shares ETF Trust III"),
    ("0000038777", "Franklin Custodian Funds"),
    ("0001582984", "Janus Henderson ETF Trust"),
    ("0001620069", "Pacer Funds Trust"),
    ("0001685581", "Pacer Funds Trust II"),
    ("0001683862", "Innovator ETFs Trust"),
    ("0001587983", "PGIM ETF Trust"),
    ("0000915802", "Financial Investors Trust"),
    ("0001881741", "NEOS ETF Trust"),
    ("0001587984", "VictoryShares ETF Trust"),
    ("0001283333", "ALPS ETF Trust"),
    ("0001587985", "Amplify ETF Trust"),
    ("0001725210", "Grayscale Ethereum Staking ETF"),
    ("0001110805", "Nuveen ETF Trust"),
    ("0001579982", "ARK ETF Trust"),
    ("0001644419", "Northern Lights Fund Trust IV"),
    ("0001644418", "Simplify ETF Trust"),
    ("0001350488", "John Hancock Exchange-Traded Fund Trust"),
    ("0001350489", "Eaton Vance ETF Trust"),
    ("0001540305", "ETF Series Solutions"),
    ("0001566219", "BMO ETF Trust"),
    ("0001587987", "Columbia ETF Trust"),
    ("0001587988", "Principal Exchange-Traded Funds"),
    ("0001924868", "Tidal Trust II"),
    ("0001934941", "F/m ETF Trust"),
    ("0001771146", "ETF Opportunities Trust"),
    ("0001771147", "Defiance ETF Trust"),
    ("0001877260", "BondBloxx ETF Trust"),
]

CIK_LOOKUP = {}
for cik, name in CIK_ENTRIES:
    if cik not in CIK_LOOKUP:
        CIK_LOOKUP[cik] = name

CIKS = list(CIK_LOOKUP.keys())


def infer_cik_group_name(name):
    lower_name = name.lower()

    if "blackrock" in lower_name or "ishares" in lower_name:
        return "BlackRock"
    if "vanguard" in lower_name:
        return "Vanguard"
    if "spdr" in lower_name:
        return "SPDR"
    if "wisdomtree" in lower_name:
        return "WisdomTree"
    if "invesco" in lower_name or "db commodity index tracking fund" in lower_name:
        return "Invesco"
    if "direxion" in lower_name:
        return "Direxion"
    if "schwab" in lower_name:
        return "Schwab"
    if "jpmorgan" in lower_name:
        return "JPMorgan"
    if "investment managers series trust" in lower_name:
        return "Investment Managers Series"
    if "first trust" in lower_name:
        return "First Trust"
    if "vaneck" in lower_name:
        return "VanEck"
    if "fidelity" in lower_name:
        return "Fidelity"
    if "american funds" in lower_name or "capital group" in lower_name:
        return "Capital Group / American Funds"
    if "american century" in lower_name:
        return "American Century"
    if "proshares" in lower_name:
        return "ProShares"
    if "profunds" in lower_name:
        return "ProFunds"
    if "global x" in lower_name:
        return "Global X"
    if "goldman sachs" in lower_name:
        return "Goldman Sachs"
    if "franklin" in lower_name:
        return "Franklin Templeton"
    if "janus henderson" in lower_name or lower_name.startswith("janus "):
        return "Janus Henderson"
    if "pacer" in lower_name:
        return "Pacer"
    if "innovator" in lower_name:
        return "Innovator"
    if "pgim" in lower_name:
        return "PGIM"
    if "financial investors trust" in lower_name:
        return "Financial Investors Trust"
    if "neos" in lower_name:
        return "NEOS"
    if "victoryshares" in lower_name:
        return "VictoryShares"
    if lower_name.startswith("alps"):
        return "ALPS"
    if "amplify" in lower_name:
        return "Amplify"
    if "grayscale" in lower_name:
        return "Grayscale"
    if "nuveen" in lower_name:
        return "Nuveen"
    if lower_name.startswith("ark "):
        return "ARK"
    if "northern lights" in lower_name:
        return "Northern Lights"
    if "simplify" in lower_name:
        return "Simplify"
    if "john hancock" in lower_name:
        return "John Hancock"
    if "eaton vance" in lower_name:
        return "Eaton Vance"
    if "etf series solutions" in lower_name:
        return "ETF Series Solutions"
    if lower_name.startswith("bmo"):
        return "BMO"
    if "columbia" in lower_name:
        return "Columbia"
    if "principal" in lower_name:
        return "Principal"
    if "tidal" in lower_name:
        return "Tidal"
    if lower_name.startswith("f/m"):
        return "F/m"
    if "etf opportunities" in lower_name:
        return "ETF Opportunities"
    if "defiance" in lower_name:
        return "Defiance"
    if "bondbloxx" in lower_name:
        return "BondBloxx"

    return name


CIK_GROUP_LOOKUP = {}
CIK_GROUP_ENTRIES = []
for cik, name in CIK_LOOKUP.items():
    group_name = infer_cik_group_name(name)
    if group_name not in CIK_GROUP_LOOKUP:
        CIK_GROUP_LOOKUP[group_name] = []
        CIK_GROUP_ENTRIES.append((group_name, CIK_GROUP_LOOKUP[group_name]))
    CIK_GROUP_LOOKUP[group_name].append(cik)

CIK_GROUP_OPTIONS = [group_name for group_name, _ in CIK_GROUP_ENTRIES]
FORMS = ["S-1", "N-1A", "485BPOS", "485APOS"]
DAYS_BACK = 60
REQUEST_DELAY_SECONDS = 0.35
INDEX_PAGE_MAX_CHARS = 60000
DATA_VERSION = "2026-03-30-ticker-sanitize-and-filing-briefs"
ETFCOM_DATA_VERSION = "2026-03-31-etfcom-etfdb-deeper-rails"
INVALID_TICKERS = {"CIK", "ETF", "FUND"}
NEWS_QUERIES = (
    "ETF launches Reuters Bloomberg MarketWatch CNBC Yahoo Finance Morningstar WSJ",
    "ETF news Reuters Bloomberg MarketWatch CNBC Yahoo Finance Morningstar WSJ",
    "ETF inflows Reuters Bloomberg MarketWatch CNBC Yahoo Finance Morningstar WSJ",
    "new ETFs Reuters Bloomberg MarketWatch CNBC Yahoo Finance Morningstar WSJ",
)
TRUSTED_NEWS_SOURCES = {
    "reuters": "Reuters",
    "bloomberg": "Bloomberg",
    "marketwatch": "MarketWatch",
    "pensions & investments": "Pensions & Investments",
    "pensions and investments": "Pensions & Investments",
    "cnbc": "CNBC",
    "msnbc": "MSNBC",
    "yahoo finance": "Yahoo Finance",
    "morningstar": "Morningstar",
    "wall street journal": "WSJ",
    "wsj": "WSJ",
    "dow jones": "Dow Jones",
    "the motley fool": "The Motley Fool",
    "motley fool": "The Motley Fool",
}
COMMON_MATCH_WORDS = {
    "etf",
    "fund",
    "trust",
    "daily",
    "long",
    "short",
    "ultra",
    "capital",
    "shares",
    "index",
    "income",
    "growth",
    "target",
}
