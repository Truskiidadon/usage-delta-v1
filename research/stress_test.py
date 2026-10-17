import pandas as pd, numpy as np
pd.set_option('display.width',240)
P=pd.read_parquet('data/stress.parquet')
P=P[P.bucket.isin(['tough','soft'])].copy()
P['half']=np.where(P.week<=9,1,2)

g=P.groupby(['season','pid','half','bucket']).agg(n=('share','size'),sh=('share','mean')).reset_index()
w=g.pivot_table(index=['season','pid','half'],columns='bucket',values=['n','sh'])
w.columns=[f'{a}_{b}' for a,b in w.columns]; w=w.reset_index()
w=w.dropna()
MIN=3
w=w[(w.n_tough>=MIN)&(w.n_soft>=MIN)]
w['gap']=w.sh_tough-w.sh_soft
h=w.pivot_table(index=['season','pid'],columns='half',values='gap')
h.columns=['h1','h2']; h=h.dropna()
print(f'players with {MIN}+ tough and {MIN}+ soft games in BOTH halves: {len(h)}')
if len(h)>20:
    r=h.h1.corr(h.h2)
    print(f'split-half correlation of the gap:  r = {r:.4f}   (bar was 0.15)')
    # also: does baseline share persist, as a sanity control?
    s=w.pivot_table(index=['season','pid'],columns='half',values='sh_soft').dropna()
    s.columns=['h1','h2']
    print(f'control — soft-game share persists:  r = {s.h1.corr(s.h2):.4f}')
print()
# relax the minimum to widen the sample
for MIN in [2,3,4]:
    ww=w if MIN==3 else None
    q=g.pivot_table(index=['season','pid','half'],columns='bucket',values=['n','sh'])
    q.columns=[f'{a}_{b}' for a,b in q.columns]; q=q.reset_index().dropna()
    q=q[(q.n_tough>=MIN)&(q.n_soft>=MIN)]
    q['gap']=q.sh_tough-q.sh_soft
    hh=q.pivot_table(index=['season','pid'],columns='half',values='gap').dropna()
    if len(hh)>20:
        hh.columns=['h1','h2']
        print(f'min {MIN} per bucket per half: n={len(hh):>5}  r={hh.h1.corr(hh.h2):+.4f}')
