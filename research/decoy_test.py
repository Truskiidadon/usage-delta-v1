import sys,numpy as np,pandas as pd
sys.path.insert(0,'/home/claude/usage-delta-v1')
pd.set_option('display.width',240)
from usage_delta import fetch
from usage_delta.diff import POSITION_PROFILES

rows=[]
for yr in range(2013,2026):
    try:
        st=pd.read_parquet(fetch.WEEKLY_STATS.format(season=yr))
        if 'receiving_air_yards' not in st.columns: print(yr,'no air yards'); continue
        u=fetch.build_usage(yr)
        ay=st[['season','week','player_id','receiving_air_yards']]
        u=u.merge(ay,left_on=['season','week','gsis_id'],right_on=['season','week','player_id'],how='left')
        rows.append(u)
    except Exception as e: print(yr,'skip',str(e)[:70])
U=pd.concat(rows,ignore_index=True)
U=U[U.position.isin(['WR','TE'])].copy()          # decoy is a pass-catcher concept
U['receiving_air_yards']=U.receiving_air_yards.fillna(0)
U=U.sort_values(['pfr_player_id','season','week'])
print('rows',len(U))

inter=U.position.map(lambda p:POSITION_PROFILES[p][0]); slope=U.position.map(lambda p:POSITION_PROFILES[p][1])
U['opp_resid']=U.opp_share-(inter+slope*U.offense_pct)

# trailing 4-week profile, no lookahead
g=U.groupby(['pfr_player_id','season'],sort=False)
for c in ['receiving_air_yards','targets','receptions','opp_share']:
    U['t_'+c]=g[c].transform(lambda s:s.rolling(4,min_periods=3).sum())
U['aDOT']=U.t_receiving_air_yards/U.t_targets.where(U.t_targets>=6)
U['catch']=U.t_receptions/U.t_targets.where(U.t_targets>=6)

# forward 4 weeks
fwd=[]
for (pid,ssn),gg in U.groupby(['pfr_player_id','season'],sort=False):
    w=gg.week.to_numpy(); o=gg.opp_share.to_numpy(); p=gg.fantasy_points_ppr.fillna(0).to_numpy()
    for i,wk in enumerate(w):
        m=(w>wk)&(w<=wk+4)
        fwd.append((gg.index[i], o[m].mean() if m.any() else np.nan, p[m].mean() if m.any() else np.nan))
f=pd.DataFrame(fwd,columns=['idx','opp_next','ppr_next']).set_index('idx')
U=U.join(f)
U['opp_gain']=U.opp_next-U.opp_share

# POPULATION: on the field, under-used
P=U[(U.offense_pct>=0.50)&(U.opp_resid<0)&U.aDOT.notna()&U.opp_gain.notna()].copy()
print('population (snap>=50%, negative residual, 6+ trailing targets):',len(P))
P['aq']=P.groupby(['season','position']).aDOT.transform(lambda s:pd.qcut(s,3,labels=False,duplicates='drop'))
P['decoy']=(P.aq==2)&(P.catch<P.groupby(['season','position']).catch.transform('median'))
P['dud']=(P.aq==0)

for nm,d in [('TUNE',P[P.season<2020]),('HOLDOUT',P[P.season>=2020])]:
    a=d[d.decoy]; b=d[d.dud]
    print(f'--- {nm} ---  decoys n={len(a)}  duds n={len(b)}')
    print(f'   opp share gain, next 4wk :  decoy {100*a.opp_gain.mean():+.2f}pp   dud {100*b.opp_gain.mean():+.2f}pp   diff {100*(a.opp_gain.mean()-b.opp_gain.mean()):+.2f}pp')
    print(f'   PPR/gm, next 4wk         :  decoy {a.ppr_next.mean():.2f}       dud {b.ppr_next.mean():.2f}       diff {a.ppr_next.mean()-b.ppr_next.mean():+.2f}')
    print(f'   aDOT                     :  decoy {a.aDOT.mean():.1f}          dud {b.aDOT.mean():.1f}')
