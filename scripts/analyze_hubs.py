#!/usr/bin/env python3
import json, datetime as dt, collections
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'docs'/'data.json'
with p.open() as f:
    data=json.load(f)

today=dt.date(2026,4,8)
end=today+dt.timedelta(days=90)
venue_counts=collections.Counter()
venue_nextdate={}
monthly_counts=collections.Counter()
by_title=collections.defaultdict(list)

for ev in data:
    title=(ev.get('title') or '').strip()
    occs=ev.get('occurrences') or []
    if occs:
        try:
            d0=dt.date.fromisoformat(occs[0]['date'])
            monthly_counts[(d0.year, d0.month)] += 1
        except Exception:
            pass
    for oc in occs:
        dstr=oc.get('date')
        if not dstr: continue
        try:
            d=dt.date.fromisoformat(dstr)
        except Exception:
            continue
        venue = (oc.get('venue') or ev.get('venue') or 'Unknown')
        by_title[title].append((d.isoformat(), venue))
        if today <= d <= end:
            venue_counts[venue]+=1
            if venue not in venue_nextdate or d < venue_nextdate[venue]:
                venue_nextdate[venue]=d

# Build consolidation insights
multi_day_titles={t:sorted({d for d,_ in lst}) for t,lst in by_title.items() if len({d for d,_ in lst})>1}
# same-day multi-venue
same_day_multivenue=[]
for t,lst in by_title.items():
    day_to_venues=collections.defaultdict(set)
    for d,v in lst:
        day_to_venues[d].add(v)
    for d,vs in day_to_venues.items():
        if len(vs)>1:
            same_day_multivenue.append((t,d,sorted(vs)))

print('TOP_HUBS')
for v,c in venue_counts.most_common(10):
    nd = venue_nextdate.get(v)
    print(f"{v}\t{c}\t{nd.isoformat() if nd else '-'}")
print('\nMONTHLY_COUNTS')
for (y,m),c in sorted(monthly_counts.items()):
    print(f"{y}-{m:02d}\t{c}")
print('\nCONSOLIDATION')
print('multi_day_titles_count', len(multi_day_titles))
print('same_day_multivenue_count', len(same_day_multivenue))
print('EXAMPLES_multi_day_titles')
for i,(t,days) in enumerate(list(multi_day_titles.items())[:5]):
    print(f"- {t}: {', '.join(days[:5])}{' ...' if len(days)>5 else ''}")
print('EXAMPLES_same_day_multivenue')
for i,(t,d,vs) in enumerate(same_day_multivenue[:5]):
    print(f"- {d}: {t} @ {', '.join(vs)}")
