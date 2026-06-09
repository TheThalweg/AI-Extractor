import os
import json
import concurrent.futures
from bs4 import BeautifulSoup
import ollama

DATA_DIR = "./Data" 
OUTPUT_FILE = "classified_emails.json"
FAILED_LOG_FILE = "failed_emails.json"

# --- Taxonomy Definitions ---
TAXONOMY_PATH = "taxonomy.json"
with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
    TAXONOMY_DATA = json.load(f).get("asset_taxonomy", {})

VALID_ASSET_TAGS = set(TAXONOMY_DATA.keys())
for sub_tags in TAXONOMY_DATA.values():
    VALID_ASSET_TAGS.update(sub_tags)

VALID_INDUSTRIES = {
    "BASIC MATERIALS": ["Agriculture", "Chemicals", "Metals & Mining", "Paper & Forest", "Steel"],
    "CONSUMER STAPLES": ["Beverages", "Consumer Products", "Food", "Retail", "Tobacco"],
    "CONSUMER CYCLICALS": ["Automobiles", "Branded Consumer Goods", "Business Services", "Consumer Durables", "Education", "Entertainment & Leisure", "Gaming", "Housing", "Lodging", "Media", "Restaurants & Pubs", "Retail", "Textile, Apparel & Footwear", "Travel"],
    "ENERGY": ["Clean Energy", "Energy", "Gas", "Oil", "Oil Services"],
    "FINANCIAL SERVICES": ["Banks", "Brokers & Asset Managers", "Capital Markets", "Diversified Financials", "Insurance", "Real Estate", "Specialty Finance"],
    "HEALTHCARE": ["Biotechnology", "Healthcare Services", "Life Sciences", "Medical Technology", "Pharmaceuticals"],
    "INDUSTRIALS": ["Aerospace & Defense", "Capital Goods", "Construction", "Electrical Equipment", "Environmental Services", "Machinery", "Multi-Industry", "Packaging"],
    "TECHNOLOGY": ["Communications Technology", "Hardware", "Info Services", "Internet", "IT Services", "Semiconductors", "Software", "Technology"],
    "TELECOM SERVICES": ["Communication Services", "Satellite", "Telecom Services", "Telecom Wireless", "Towers"],
    "TRANSPORTATION": ["Air Freight", "Airlines", "Airports", "Infrastructure", "Logistics", "Railroads", "Shipping", "Trucking"],
    "UTILITIES": ["Diversified", "Gas", "MLPs", "Power", "Utilities", "Water"]
}

SYSTEM_PROMPT = """
You are an expert financial analyst assistant. Your job is to classify market research emails.
You must respond ONLY with a single, valid JSON object matching the requested schema. No conversational filler text.

The returned JSON should have the following info:
folder_name Subject / title of the research note
bank - Publishing investment bank
date - Publication date (YYYY-MM-DD)
market_wrap YES or NO — see Market Wrap rules below
primary_asset_tag - The single most important asset class tag
asset_tags - Array of ALL relevant tags (primary + sub-tags)
companies_mentioned - Array of companies materially discussed (Only if there is an Equity tag - e.g. "companies_mentioned": [
            "ITX.MC",
            "Inditex"
        ],)
industry_subindustry - Array of sector > subindustry strings (Equity only) e.g. ENERGY > gas


Follow these classification rules strictly:
1. MARKET WRAP RULE: Determine if the email is a Market Wrap (a short daily recap of market moves, cross-asset, multi-region, short bullet points). 
   - If YES: set market_wrap="YES", primary_asset_tag="Market Wrap", asset_tags=["Market Wrap"], companies_mentioned=[], and industry_subindustry=[].
   - If NO: set market_wrap="NO" and proceed to rules 2 and 3.

Use the following roles to determine whether an email is a Market Wrap. If the majority of the rules are followed, it is a market wrap.:
  Structure - Does the article cover multiple regions (US, Europe, Asia)?
  - Does the article include multiple sections by geography?
  - Does the article summarise several markets in sequence?
  - Does the article include short bullet-point updates across topics?
  Asset Coverage - Does the article reference multiple asset classes (equities, bonds, FX, 
  commodities)?
  - Are different markets discussed briefly rather than in depth?
  Timeframe - Does the article summarise what happened in the previous trading session?
  - Is the content focused on recent or overnight market moves?
  Purpose - Is the article descriptive rather than analytical?
  - Does the article lack a clear forward-looking investment view?
  Title - Does the title include terms like “Market Wrap”, “Morning Note”, “Daily 
  Update”, “Market Recap”?
  Language - Is summary-style market language used across multiple sections of the 
  article?
  - Are multiple asset classes described using short, descriptive statements (e.g., 
  equities fell, yields moved, FX weakened)?
  - Is the language consistently descriptive rather than analytical throughout the 
  article?
  Depth - Are topics covered briefly without deep explanation?
  - Are multiple unrelated updates grouped together in one note?


2. ASSET TAGGING TAXONOMY (Only if Market Wrap = NO):
   - Macro [Sub-tags: Developed Markets, Emerging Markets]
   - Fixed Income [Sub-tags: Credit Strategy, Rates Strategy, Securitisation]
   - Equity [Sub-tags: Company Research, Portfolio Strategy, Thematic Investing]
   - Commodities [Sub-tags: Energy, Metals, Agriculture]
   - FX [Sub-tags: USD, EUR, JPY, GBP, CHF, Other]
   - Thematics [No sub-tags]
   Only assign a tag/sub-tag if it is MATERIALIZED and discussed meaningfully, not just passing mentions. Only use the given tags

3. INDUSTRY TAGGING TAXONOMY (Only if Equity tag is applied AND specific companies/sectors are discussed):
   Format must be "SECTOR > Subindustry" (e.g., "TECHNOLOGY > Software", "FINANCIAL SERVICES > Banks"). If indiscernible, use "Unknown".
   
   Permitted Sectors and Subindustries:
   - BASIC MATERIALS > Agriculture; Chemicals; Metals & Mining; Paper & Forest; Steel
   - CONSUMER STAPLES > Beverages; Consumer Products; Food; Retail; Tobacco
   - CONSUMER CYCLICALS > Automobiles; Branded Consumer Goods; Business Services; Consumer Durables; Education; Entertainment & Leisure; Gaming; Housing; Lodging; Media; Restaurants & Pubs; Retail; Textile, Apparel & Footwear; Travel
   - ENERGY > Clean Energy; Energy; Gas; Oil; Oil Services
   - FINANCIAL SERVICES > Banks; Brokers & Asset Managers; Capital Markets; Diversified Financials; Insurance; Real Estate; Specialty Finance
   - HEALTHCARE > Biotechnology; Healthcare Services; Life Sciences; Medical Technology; Pharmaceuticals
   - INDUSTRIALS > Aerospace & Defense; Capital Goods; Construction; Electrical Equipment; Environmental Services; Machinery; Multi-Industry; Packaging
   - TECHNOLOGY > Communications Technology; Hardware; Info Services; Internet; IT Services; Semiconductors; Software; Technology
   - TELECOM SERVICES > Communication Services; Satellite; Telecom Services; Telecom Wireless; Towers
   - TRANSPORTATION > Air Freight; Airlines; Airports; Infrastructure; Logistics; Railroads; Shipping; Trucking
   - UTILITIES > Diversified; Gas; MLPs; Power; Utilities; Water
   
  Do not include anything in the companies_mentioned unless equity is in the asset_tags
   
"""

def extract_email_data(html_path):
    """Reads an HTML file and extracts raw metadata and stripped text."""
    folder_path = os.path.dirname(html_path)
    folder_name = os.path.basename(folder_path)
    file_name = os.path.basename(html_path)

    # Find PDF attachments if present
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
    pdf_attachment = pdf_files if pdf_files else None

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except UnicodeDecodeError:
        # Fallback to latin-1 for documents with legacy character encoding
        with open(html_path, "r", encoding="latin-1") as f:
            html_content = f.read()

    # Clean the HTML to save token space for Llama 3
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Strip script and style tags
    for script in soup(["script", "style"]):
        script.decompose()
        
    clean_text = soup.get_text(separator=" ")
    # Clean up whitespace
    clean_text = " ".join(clean_text.split())

    return {
        "source_file": folder_name if folder_name != os.path.basename(DATA_DIR) else "Root", # confusingly this is the folder name
        "pdf_attachment": pdf_attachment,
        "clean_text": clean_text[:8000] # Cap text slice to protect context window limits
    }

def analyze_with_llama(email_text):
    """Sends clean text to Llama 3 enforcing a native JSON structure response."""
    user_prompt = f"Analyze the following financial research text and classify it:\n\n{email_text}"

    # Uses ThreadPoolExecutor to enforce a 2-minute (120s) timeout
    # I had one of the classifications take 10 minutes and then it gave back an error anyway so this handles that
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            ollama.chat,
            model="llama3",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            format="json",
            options={"temperature": 0.0}
        )
        try:
            response = future.result(timeout=120)
            # Parse the JSON string from Llama 3 into a Python Dict
            return json.loads(response.message.content)
        except concurrent.futures.TimeoutError:
            raise Exception("Llama 3 classification timed out after 120 seconds")
        except Exception as e:
            raise Exception(f"LLM analysis error: {e}")

# Sometimes the AI spits out something formatted incorrectly so this is just to correct the format
# This doesn't fix the fact that some of the companies the AI spits out are the same but named slightly differently
# This could probably be fixed by having another run through an LLM, identifying the company names that are the same and 
# normalising it. I left this out as I didn't think it was necessary for the task
def sanitize_entry(entry):
    # Enforces market wrap requirements
    is_wrap = str(entry.get("market_wrap", "NO")).upper() == "YES"
    if is_wrap:
        entry["market_wrap"] = "YES"
        entry["primary_asset_tag"] = "Market Wrap"
        entry["asset_tags"] = ["Market Wrap"]
        entry["companies_mentioned"] = []
        entry["industry_subindustry"] = []
        return entry

    # Sometimes the AI spat out a array of {name: Company} entries so this handles that
    raw_companies = entry.get("companies_mentioned", [])
    clean_companies = []
    if isinstance(raw_companies, list):
        for item in raw_companies:
            if isinstance(item, dict):
                name = item.get("name") or item.get("company")
                if name: clean_companies.append(str(name))
            elif isinstance(item, str):
                clean_companies.append(item)
    entry["companies_mentioned"] = list(set(clean_companies)) # Deduplicate

    # Similar to companies mentioned cleaning
    raw_industries = entry.get("industry_subindustry", [])
    clean_industries = []
    if isinstance(raw_industries, list):
        for item in raw_industries:
            # Handles object format: {"sector": "...", "subindustry": "..."}
            if isinstance(item, dict):
                sec, sub = item.get("sector"), item.get("subindustry")
                if sec and sub: clean_industries.append(f"{sec} > {sub}")
            # Handles list format: ["TECH", "Software"]
            elif isinstance(item, list) and len(item) >= 2:
                clean_industries.append(f"{item[0]} > {item[1]}")
            elif isinstance(item, str):
                clean_industries.append(item)
    
    # Filter and validate industries by sector and subindustry taxonomy
    # Sometimes the AI was hallucinating industries despite me telling it the allowed industries
    sanitized_industries = []
    for ind in clean_industries:
        if " > " in ind:
            parts = [p.strip() for p in ind.split(" > ", 1)]
            sec_key = parts[0].upper()
            sub_val = parts[1]
            
            if sec_key in VALID_INDUSTRIES:
                # Case-insensitive check for subindustry
                valid_subs_lower = [s.lower() for s in VALID_INDUSTRIES[sec_key]]
                if sub_val.lower() in valid_subs_lower:
                    # Map back to the correctly cased version from the taxonomy
                    correct_sub = VALID_INDUSTRIES[sec_key][valid_subs_lower.index(sub_val.lower())]
                    sanitized_industries.append(f"{sec_key} > {correct_sub}")
    
    entry["industry_subindustry"] = list(set(sanitized_industries))

    # Same as before but with assets. Also ensures primary tag is included in asset tags
    primary = entry.get("primary_asset_tag", "Unknown")
    tags = entry.get("asset_tags", [])
    
    if primary not in VALID_ASSET_TAGS:
        primary = "Unknown"
    
    valid_tags = list(set([t for t in tags if t in VALID_ASSET_TAGS]))
    if primary != "Unknown" and primary not in valid_tags:
        valid_tags.append(primary)
        
    entry["primary_asset_tag"] = primary
    entry["asset_tags"] = valid_tags

    # Ensures that we only have companies and industries when we have an equity tag
    if "Equity" not in entry["asset_tags"]:
        entry["companies_mentioned"] = []
        entry["industry_subindustry"] = []
        
    return entry

def main():
    classified_results = []
    failed_results = []

    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory '{DATA_DIR}' not found. Please create it or adjust config.")
        return

    print("Starting classification pipeline...")
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            if not file.lower().endswith(".html"):
                continue

            html_path = os.path.join(root, file)
            try:
                extracted = extract_email_data(html_path)
                classification = analyze_with_llama(extracted["clean_text"])
                
                if classification:
                    # Merge AI result with local metadata and sanitize
                    raw_entry = {
                        **classification,
                        "folder_name": classification.get("folder_name") or extracted["source_file"],
                        "bank": classification.get("bank", "Unknown"),
                        "pdf_attachment": extracted["pdf_attachment"],
                        "source_file": extracted["source_file"]
                    }
                    
                    final_entry = sanitize_entry(raw_entry)
                    
                    classified_results.append(final_entry)
                    print(f"\n--- Classified Entry: {extracted['source_file']} ---")
                    print(json.dumps(final_entry, indent=4))
                else:
                    raise Exception("Ollama did not return a valid classification object.")
            except Exception as e:
                print(f"Error processing {html_path}: {e}")
                # Record failed results so we can fix it later
                failed_results.append({
                    "file": html_path,
                    "error": str(e)
                })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(classified_results, f, indent=4, ensure_ascii=False)

    if failed_results:
        with open(FAILED_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_results, f, indent=4, ensure_ascii=False)

    print(f"Pipeline complete! Saved results to {OUTPUT_FILE}")
    if failed_results:
        print(f"Failures recorded: {len(failed_results)}. See {FAILED_LOG_FILE}")
        
# The original run took 2 hours so I just ran this to sanitize the incorrectly formatted data afterthefact
def sanitize_existing_json(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    cleaned_data = [sanitize_entry(entry) for entry in data]
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_data, f, indent=4)
    print(f"Successfully sanitized {len(cleaned_data)} entries in {file_path}")

if __name__ == "__main__":
    main()