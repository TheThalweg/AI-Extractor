import os
import json
from bs4 import BeautifulSoup
import ollama

DATA_DIR = "./Data" 
OUTPUT_FILE = "classified_emails.json"

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
companies_mentioned - Array of companies materially discussed (Only if there is an Equity tag)
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
   Only assign a tag/sub-tag if it is MATERIALIZED and discussed meaningfully, not just passing mentions.

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

    with open(html_path, "r", encoding="utf-8") as f:
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
    
    try:
        response = ollama.chat(
            model="llama3",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            format="json", 
            options={"temperature": 0.0} # we hate creativity
        )
        
        # Parse the JSON string from Llama 3 into a Python Dict
        return json.loads(response.message.content)
    except Exception as e:
        print(f"Error calling Llama 3: {e}")
        return None

def main():
    classified_results = []

    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory '{DATA_DIR}' not found. Please create it or adjust config.")
        return

    print("Starting classification pipeline...")
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            if not file.lower().endswith(".html"):
                continue

            html_path = os.path.join(root, file)

            extracted = extract_email_data(html_path)
            classification = analyze_with_llama(extracted["clean_text"])
            
            if classification:
                primary = classification.get("primary_asset_tag", "Unknown")
                tags = classification.get("asset_tags", [])
                
                # Ensures primary tag is included in the asset tags list
                if primary != "Unknown" and primary not in tags:
                    tags.append(primary)
                
                # Company + industry tags only allowed when "Equity" is in the asset tags
                # Sometimes the AI is stupid and includes it anyway 
                # Would rather a correct system than a fast one
                has_equity = any("Equity" in str(tag) for tag in tags)
                companies = classification.get("companies_mentioned", []) if has_equity else []
                industries = classification.get("industry_subindustry", []) if has_equity else []

                final_entry = {
                    "folder_name": classification.get("folder_name", "Unknown"),
                    "bank": classification.get("bank", "Unknown"),
                    "date": classification.get("date", "Unknown"),
                    "market_wrap": classification.get("market_wrap", "NO"),
                    "primary_asset_tag": primary,
                    "asset_tags": tags,
                    "companies_mentioned": companies,
                    "industry_subindustry": industries,
                    "pdf_attachment": extracted["pdf_attachment"],
                    "source_file": extracted["source_file"]
                }
                classified_results.append(final_entry)
                print(f"\n--- Classified Entry: {extracted['source_file']} ---")
                print(json.dumps(final_entry, indent=4))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(classified_results, f, indent=4)
        
    print(f"Pipeline complete! Saved results to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()