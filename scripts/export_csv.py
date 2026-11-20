"""Export canonical records to CSVs shaped for the Google Sheet tabs."""
import csv, json, sys
sys.path.insert(0, '/home/sandbox/aisignal-pipeline')
from src.storage import Store

KINDS = {"startups": "STARTUP", "products": "PRODUCT", "papers": "RESEARCH_PAPER",
         "jobs": "JOB", "news": "NEWS"}

def main():
    s = Store()
    for kind, rtype in KINDS.items():
        recs = s.records(rtype)
        with open(f'exports/{kind}.csv', 'w', newline='', encoding='utf-8') as f:
            if kind == 'startups':
                w = csv.writer(f)
                w.writerow(['schemaVersion','recordType','entityName','website','description','batch','location','tags','employeeCount','source.name','source.url','collectedAt'])
                for r in recs:
                    c = r['content']
                    w.writerow([r['schemaVersion'], r['recordType'], c['entityName'], c.get('website'), c.get('description'), c.get('batch'), c.get('location'), '; '.join(c.get('tags',[])), (c.get('data') or {}).get('employeeCount'), r['source']['name'], r['source']['url'], r['collectedAt']])
            elif kind == 'products':
                w = csv.writer(f)
                w.writerow(['schemaVersion','recordType','productName','startupName','description','pricingModel','categories','source.name','source.url','collectedAt'])
                for r in recs:
                    c = r['content']
                    w.writerow([r['schemaVersion'], r['recordType'], c['productName'], c.get('startupName'), c.get('description'), c.get('pricingModel'), '; '.join(c.get('categories',[])), r['source']['name'], r['source']['url'], r['collectedAt']])
            elif kind == 'papers':
                w = csv.writer(f)
                w.writerow(['schemaVersion','recordType','title','authors','paper_url','github_url','github_stars','stars_source','published_date','source.name','source.url','collectedAt'])
                for r in recs:
                    c = r['content']
                    w.writerow([r['schemaVersion'], r['recordType'], c['title'], '; '.join(c.get('authors',[])), c.get('paper_url'), c.get('github_url'), c.get('github_stars'), c.get('stars_source'), c.get('published_date'), r['source']['name'], r['source']['url'], r['collectedAt']])
            elif kind == 'jobs':
                w = csv.writer(f)
                w.writerow(['schemaVersion','recordType','title','company','date','url','location','is_remote','role_family','source.name','collectedAt'])
                for r in recs:
                    c = r['content']
                    w.writerow([r['schemaVersion'], r['recordType'], c['title'], c['company'], c['date'], c['url'], c.get('location'), c['is_remote'], c['role_family'], r['source']['name'], r['collectedAt']])
            elif kind == 'news':
                w = csv.writer(f)
                w.writerow(['schemaVersion','recordType','headline','url','published_date','date_confidence','source.name','summary','collectedAt'])
                for r in recs:
                    c = r['content']
                    w.writerow([r['schemaVersion'], r['recordType'], c['headline'], c['url'], c['published_date'], c.get('date_confidence'), r['source']['name'], (c.get('full_text') or '')[:400], r['collectedAt']])
        print(kind, len(recs))
    with open('exports/entity_map.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['raw_name','canonical_name','record_type','match_strategy','confidence','decided_at'])
        for row in s.mappings():
            w.writerow(row)
    print('entity_map', len(s.mappings()))

if __name__ == '__main__':
    main()
