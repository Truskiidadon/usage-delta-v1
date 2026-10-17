import sys,numpy as np,pandas as pd
sys.path.insert(0,'/home/claude/usage-delta-v1')
pd.set_option('display.width',230)
from usage_delta import backtest as bt
from usage_delta.diff import MIN_SNAPS, _tier
U=pd.read_pickle('data/usage_all.pkl')
U=U[U.position.isin(['WR','RB','TE'])].sort_values(['pfr_player_id','season','week']).copy()
U['fantasy_points_ppr']=U.fantasy_points_ppr.fillna(0)

TUNE=U.season<2020
print('=== conversion of snaps into opportunity, by position (TUNE fit) ===')
prof={}
for pos in ['RB','WR','TE']:
    d=U[TUNE&U.position.eq(pos)&(U.offense_pct>0.05)]
    b,a=np.polyfit(d.offense_pct,d.opp_share,1)
    r=np.corrcoef(d.offense_pct,d.opp_share)[0,1]
    prof[pos]=(a,b)
    print(f'  {pos}: opp_share = {a:+.4f} + {b:.4f} * snap_share   r={r:.3f}  n={len(d)}')
    print(f'       at 50% snaps -> {a+b*0.5:.3f} opp share;  at 90% -> {a+b*0.9:.3f}')

U['opp_expected']=[prof[p][0]+prof[p][1]*s if p in prof else np.nan
                   for p,s in zip(U.position,U.offense_pct)]
U['opp_resid']=U.opp_share-U.opp_expected

g=U.groupby(['pfr_player_id','season'],sort=False)
for c in ['offense_pct','opp_share','opp_resid']:
    U[c+'_prior']=g[c].shift(1); U[c+'_delta']=U[c]-U[c+'_prior']
U['baseline_ppr']=g.fantasy_points_ppr.transform(lambda s:s.shift(1).rolling(3,min_periods=1).mean())
out=[]
for (pid,ssn),gg in U.groupby(['pfr_player_id','season'],sort=False):
    w=gg.week.to_numpy(); p=gg.fantasy_points_ppr.to_numpy()
    for i,wk in enumerate(w):
        m=(w>wk)&(w<=wk+4)
        out.append((gg.index[i],m.sum(),p[m].mean() if m.any() else np.nan))
o=pd.DataFrame(out,columns=['idx','games_after','outcome_ppr']).set_index('idx')
U=U.join(o)
U['flagged']=[t in ('alert','actionable') for t in
              (_tier(d,p) for d,p in zip(U.offense_pct_delta,U.offense_pct_prior))]
U['flagged']&=U.offense_snaps>=MIN_SNAPS
U['group']=np.where(U.flagged,'flag','control')
U['baseline_bin']=pd.cut(U.baseline_ppr,bt.BASELINE_BINS)
D=U[U.baseline_ppr.notna()&(U.games_after>0)&U.outcome_ppr.notna()]
U.to_pickle('data/usage_resid.pkl')

def ctl(panel,t):
    c=panel[panel.group=='control']
    w=t.baseline_bin.value_counts(normalize=True)
    m=c.groupby('baseline_bin',observed=True).outcome_ppr.mean()
    sh=m.index.intersection(w.index)
    return float((m[sh]*(w[sh]/w[sh].sum())).sum())

def rule_raw(d,bars):
    up=d.offense_pct_delta>0; dn=d.offense_pct_delta<0
    b=d.position.map(bars)
    return (up&(d.opp_share_delta>=b))|(dn&(d.opp_share_delta<=-b))
def rule_resid(d,bar):
    up=d.offense_pct_delta>0; dn=d.offense_pct_delta<0
    return (up&(d.opp_resid_delta>=bar))|(dn&(d.opp_resid_delta<=-bar))

print()
for nm,panel in [('TUNE',D[D.season<2020]),('HOLDOUT',D[D.season>=2020])]:
    print(f'===== {nm} =====')
    print(f"{'rule':<30}{'RB':>8}{'WR':>8}{'TE':>8}{'mean':>8}")
    for label,fn in [('opp raw .08/.04/.03',lambda d: rule_raw(d,{'RB':.08,'WR':.04,'TE':.03})),
                     ('residual bar 0.02',lambda d: rule_resid(d,0.02)),
                     ('residual bar 0.03',lambda d: rule_resid(d,0.03)),
                     ('residual bar 0.04',lambda d: rule_resid(d,0.04))]:
        f=panel[panel.flagged]; row=f'{label:<30}'; tot=[]
        for pos in ['RB','WR','TE']:
            s=f[f.position.eq(pos)]; c=fn(s); a,b=s[c],s[~c]
            if len(a)<50 or len(b)<50: row+=f'{"-":>8}'; continue
            gp=(a.outcome_ppr.mean()-ctl(panel,a))-(b.outcome_ppr.mean()-ctl(panel,b))
            row+=f'{gp:>+8.2f}'; tot.append(gp)
        print(row+f'{np.mean(tot):>+8.2f}')
    print()
