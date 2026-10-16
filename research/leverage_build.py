import pandas as pd, numpy as np, time
COLS=['season','week','game_id','posteam','play_type','qtr','score_differential','wp',
      'rusher_player_id','receiver_player_id','complete_pass','rushing_yards','receiving_yards',
      'rush_touchdown','pass_touchdown','season_type']
U='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{}.parquet'
out=[]
for yr in range(2016,2026):
    t=time.time()
    try:
        d=pd.read_parquet(U.format(yr),columns=COLS)
    except Exception as e:
        print(yr,'FAIL',str(e)[:80]); continue
    d=d[(d.season_type=='REG')&d.play_type.isin(['run','pass'])&d.score_differential.notna()&d.wp.notna()]
    ru=d[d.rusher_player_id.notna()].copy(); ru['pid']=ru.rusher_player_id
    ru['ppr']=ru.rushing_yards.fillna(0)*0.1+ru.rush_touchdown.fillna(0)*6
    pa=d[d.receiver_player_id.notna()].copy(); pa['pid']=pa.receiver_player_id
    cp=pa.complete_pass.fillna(0)
    pa['ppr']=cp*1.0+pa.receiving_yards.fillna(0)*0.1+pa.pass_touchdown.fillna(0)*6
    k=pd.concat([ru[['season','week','posteam','pid','qtr','score_differential','ppr']],
                 pa[['season','week','posteam','pid','qtr','score_differential','ppr']]])
    k['clutch']=((k.qtr>=4)&(k.score_differential.abs()<=8)).astype(int)
    g=k.groupby(['season','week','posteam','pid']).agg(opp=('ppr','size'),c_opp=('clutch','sum'),pts=('ppr','sum')).reset_index()
    tm=k.groupby(['season','week','posteam']).agg(t_opp=('ppr','size'),t_c=('clutch','sum')).reset_index()
    g=g.merge(tm,on=['season','week','posteam'])
    out.append(g)
    print(yr,len(g),'player-weeks',round(time.time()-t,1),'s',flush=True)
P=pd.concat(out,ignore_index=True)
P.to_parquet('data/leverage_panel.parquet',index=False)
print('TOTAL',len(P),'rows, seasons',sorted(P.season.unique()))
