import pandas as pd, numpy as np, time
COLS=['season','week','posteam','defteam','play_type','epa','season_type',
      'rusher_player_id','receiver_player_id','complete_pass',
      'rushing_yards','receiving_yards','rush_touchdown','pass_touchdown']
U='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{}.parquet'
P=[];D=[]
for yr in range(2016,2026):
    d=pd.read_parquet(U.format(yr),columns=COLS)
    d=d[(d.season_type=='REG')&d.play_type.isin(['run','pass'])&d.defteam.notna()]
    # defensive strength: EPA allowed per play, season level
    D.append(d.groupby(['season','defteam']).epa.mean().rename('def_epa').reset_index())
    ru=d[d.rusher_player_id.notna()].copy(); ru['pid']=ru.rusher_player_id
    ru['ppr']=ru.rushing_yards.fillna(0)*0.1+ru.rush_touchdown.fillna(0)*6
    pa=d[d.receiver_player_id.notna()].copy(); pa['pid']=pa.receiver_player_id
    pa['ppr']=pa.complete_pass.fillna(0)*1.0+pa.receiving_yards.fillna(0)*0.1+pa.pass_touchdown.fillna(0)*6
    k=pd.concat([ru[['season','week','posteam','defteam','pid','ppr']],
                 pa[['season','week','posteam','defteam','pid','ppr']]])
    g=k.groupby(['season','week','posteam','defteam','pid']).agg(opp=('ppr','size'),pts=('ppr','sum')).reset_index()
    t=k.groupby(['season','week','posteam']).size().rename('t_opp').reset_index()
    P.append(g.merge(t,on=['season','week','posteam']))
    print(yr,'ok',flush=True)
P=pd.concat(P,ignore_index=True); D=pd.concat(D,ignore_index=True)
D['rank']=D.groupby('season').def_epa.rank(method='first')          # low epa allowed = tough
D['bucket']=np.where(D['rank']<=10,'tough',np.where(D['rank']>=23,'soft','mid'))
P=P.merge(D[['season','defteam','bucket','def_epa']],on=['season','defteam'])
P['share']=P.opp/P.t_opp
P.to_parquet('data/stress.parquet',index=False)
print('rows',len(P))
print(D.groupby(['season','bucket']).size().unstack().head(3).to_string())
