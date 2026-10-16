import pandas as pd, numpy as np
pd.set_option('display.width',240)
P=pd.read_parquet('data/leverage_panel.parquet')
P=P.sort_values(['season','pid','week'])
g=P.groupby(['season','pid'],sort=False)
for c in ['opp','c_opp','t_opp','t_c','pts']:
    P[c+'_cum']=g[c].cumsum()
P['recent3']=g.pts.transform(lambda s: s.rolling(3,min_periods=1).mean())
P['games']=g.cumcount()+1
P['pts_next']=g.pts.shift(-1)
P['wk_next']=g.week.shift(-1)

P['base_sh']=P.opp_cum/P.t_opp_cum
P['clutch_sh']=np.where(P.t_c_cum>0,P.c_opp_cum/P.t_c_cum,np.nan)
P['trust']=100*(P.clutch_sh-P.base_sh)

D=P[(P.games>=5)&(P.opp_cum>=25)&P.pts_next.notna()&P.trust.notna()].copy()
print('eligible player-weeks:',len(D))
print('seasons:',sorted(D.season.unique()))

tr=D[D.season<=2022]; ho=D[D.season>=2023]
print(f'train {len(tr)}  holdout {len(ho)}')

def fit(X,y):
    X=np.column_stack([np.ones(len(X)),X]); 
    b,*_=np.linalg.lstsq(X,y,rcond=None); return b
def r2(b,X,y):
    X=np.column_stack([np.ones(len(X)),X]); p=X@b
    return 1-((y-p)**2).sum()/((y-y.mean())**2).sum()

fa=['base_sh','recent3']; fb=['base_sh','recent3','trust']
ba=fit(tr[fa].values,tr.pts_next.values); bb=fit(tr[fb].values,tr.pts_next.values)
ra=r2(ba,ho[fa].values,ho.pts_next.values); rb=r2(bb,ho[fb].values,ho.pts_next.values)
print()
print('HOLDOUT R^2')
print(f'  A  base_share + recent3            {ra:.4f}')
print(f'  B  + trust                         {rb:.4f}')
print(f'  incremental                        {rb-ra:+.4f}')
print(f'  trust coefficient (train)          {bb[3]:+.4f} pts per point of trust')

# quintile lift, controlling for base share
ho=ho.copy()
ho['bq']=pd.qcut(ho.base_sh,5,labels=False,duplicates='drop')
rows=[]
for q in sorted(ho.bq.dropna().unique()):
    s=ho[ho.bq==q].copy()
    s['tq']=pd.qcut(s.trust,5,labels=False,duplicates='drop')
    lo=s[s.tq==0].pts_next.mean(); hi=s[s.tq==s.tq.max()].pts_next.mean()
    rows.append(dict(base_quintile=int(q)+1, n=len(s),
        base_sh=round(s.base_sh.mean(),3),
        low_trust_next=round(lo,2), high_trust_next=round(hi,2),
        diff=round(hi-lo,2), lift=round(hi/lo,3) if lo else np.nan))
print()
print('HOLDOUT: next-week points, bottom vs top trust quintile, within base-share quintile')
print(pd.DataFrame(rows).to_string(index=False))

print()
c=ho[['trust','base_sh','recent3','pts_next']].corr().round(3)
print('holdout correlations'); print(c.to_string())
