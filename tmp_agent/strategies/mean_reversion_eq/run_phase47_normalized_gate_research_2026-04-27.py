import json, math, itertools, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
warnings.filterwarnings('ignore')
ROOT=Path(r'C:/AI_VAULT/tmp_agent/strategies/mean_reversion_eq')
IN=ROOT/'phase46_allweekly_p33_2023_2025_2026-04-26.json'
OUT_JSON=ROOT/'phase47_normalized_gate_research_2026-04-27.json'
OUT_TXT=ROOT/'phase47_normalized_gate_research_2026-04-27.txt'
FEATURE_CSV=ROOT/'phase47_normalized_gate_features_2026-04-27.csv'
CAND='P46_ALLWEEKLY_P33_R0135'
TICKERS=['SPY','QQQ','IWM','VIXY','^VIX']


def load_rows():
    d=json.loads(IN.read_text(encoding='utf-8'))
    rows=[]
    for r in d['rows']:
        if r.get('candidate')!=CAND: continue
        ds=r['dates']; st=pd.Timestamp(ds['start_year'],ds['start_month'],ds['start_day'])
        days=r.get('days_to_6pct') or -1
        clean=(r.get('dbr') or 0)==0 and (r.get('tbr') or 0)==0
        rows.append({'window':r['window'],'start':st.strftime('%Y-%m-%d'),'np_pct':r.get('np_pct'),'dd_pct':r.get('dd_pct'),
            'dbr':r.get('dbr') or 0,'tbr':r.get('tbr') or 0,'orders':r.get('orders') or 0,'days_to_6':days,
            'pass_any':1 if clean and days>0 else 0,'pass_fast15':1 if clean and 0<days<=15 else 0,'pass_fast10':1 if clean and 0<days<=10 else 0})
    return rows


def get_data(rows):
    start=(pd.to_datetime(min(r['start'] for r in rows))-pd.Timedelta(days=180)).strftime('%Y-%m-%d')
    end=(pd.to_datetime(max(r['start'] for r in rows))+pd.Timedelta(days=5)).strftime('%Y-%m-%d')
    data={}
    cache=ROOT/'market_cache_phase47'; cache.mkdir(exist_ok=True)
    for t in TICKERS:
        fp=cache/(t.replace('^','IDX_')+'.csv')
        if fp.exists():
            df=pd.read_csv(fp,parse_dates=['Date']).set_index('Date')
        else:
            df=yf.download(t,start=start,end=end,auto_adjust=False,progress=False,threads=False,timeout=30)
            if isinstance(df.columns,pd.MultiIndex): df.columns=[c[0] for c in df.columns]
            df=df.dropna(how='all')
            df.to_csv(fp,index_label='Date')
        data[t]=df
    return data


def indicators(df):
    out=df.copy()
    out['ret1']=out['Close'].pct_change()
    for n in [3,5,10,20,50]:
        out[f'ret{n}']=out['Close'].pct_change(n)
        out[f'sma{n}']=out['Close'].rolling(n).mean()
        out[f'rsma{n}']=out['Close']/out[f'sma{n}']-1
        out[f'rv{n}']=out['ret1'].rolling(n).std()*math.sqrt(252)
        out[f'rng{n}']=((out['High']-out['Low'])/out['Close']).rolling(n).mean()
        out[f'dd{n}']=out['Close']/out['High'].rolling(n).max()-1
    out['gap1']=(out['Open']-out['Close'].shift(1))/out['Close'].shift(1)
    return out


def make_features(rows,data):
    ind={k:indicators(v) for k,v in data.items()}
    feats=[]
    for r in rows:
        dt=pd.Timestamp(r['start']); f=dict(r)
        for t,pfx in [('SPY','spy'),('QQQ','qqq'),('IWM','iwm')]:
            df=ind[t]; idx=df.index[df.index<dt]
            if not len(idx): continue
            last=idx[-1]
            for c in ['ret3','ret5','ret10','ret20','rsma20','rsma50','rv5','rv10','rv20','rng5','rng10','dd20','dd50','gap1']:
                f[f'{pfx}_{c}']=float(df.loc[last,c]) if pd.notna(df.loc[last,c]) else np.nan
        for t,pfx in [('VIXY','vixy'),('^VIX','vix')]:
            df=ind[t]; idx=df.index[df.index<dt]
            if not len(idx): continue
            last=idx[-1]
            for c in ['ret3','ret5','ret10','ret20','rsma5','rsma10','rsma20','rv5','rng5']:
                f[f'{pfx}_{c}']=float(df.loc[last,c]) if pd.notna(df.loc[last,c]) else np.nan
            f[f'{pfx}_close']=float(df.loc[last,'Close'])
        f['risk_on_breadth5']=sum(1 for k in ['spy_ret5','qqq_ret5','iwm_ret5'] if f.get(k,np.nan)>0)
        f['trend_breadth20']=sum(1 for k in ['spy_rsma20','qqq_rsma20','iwm_rsma20'] if f.get(k,np.nan)>0)
        f['qqq_minus_spy_ret5']=f.get('qqq_ret5',np.nan)-f.get('spy_ret5',np.nan)
        f['iwm_minus_spy_ret5']=f.get('iwm_ret5',np.nan)-f.get('spy_ret5',np.nan)
        feats.append(f)
    df=pd.DataFrame(feats)
    df.to_csv(FEATURE_CSV,index=False)
    return df


def eval_mask(df,mask,label,rule):
    sel=df[mask]
    if len(sel)==0: return None
    hits=int(sel[label].sum())
    return {'rule':rule,'signals':int(len(sel)),'hits':hits,'hit_rate':round(hits/len(sel),3),
        'avg_np':round(float(sel['np_pct'].mean()),3),'min_np':round(float(sel['np_pct'].min()),3),'max_dd':round(float(sel['dd_pct'].max()),3),
        'fast15_hits':int(sel['pass_fast15'].sum()),'any_hits':int(sel['pass_any'].sum()),'starts':sel['start'].tolist(),'days':[int(x) for x in sel['days_to_6'].tolist()]}


def build_clauses(df,label,min_signals):
    ignore={'window','start','np_pct','dd_pct','dbr','tbr','orders','days_to_6','pass_any','pass_fast15','pass_fast10'}
    clauses=[]; unary=[]
    for feat in [c for c in df.columns if c not in ignore and pd.api.types.is_numeric_dtype(df[c])]:
        # VIXY is a decaying/split-adjusted ETF; its absolute price is not a
        # stable state variable across years. Ratios/returns/vol are allowed.
        if feat == 'vixy_close':
            continue
        s=df[feat]
        if s.notna().sum()<20: continue
        qs=np.nanquantile(s,[0.20,0.30,0.40,0.50,0.60,0.70,0.80])
        for thr in sorted(set(float(round(q,8)) for q in qs if pd.notna(q))):
            for op in ['>=','<=']:
                mask=(s>=thr) if op=='>=' else (s<=thr)
                r=eval_mask(df,mask,label,f'{feat}{op}{thr:.6g}')
                if r and r['signals']>=min_signals:
                    clause=(feat,op,thr,mask,r)
                    clauses.append(clause); unary.append(r)
    clauses=sorted(clauses,key=lambda x:(x[4]['hit_rate'],x[4]['hits'],x[4]['signals'],x[4]['avg_np']),reverse=True)[:120]
    return clauses,unary


def search(df,label,min_signals):
    clauses,unary=build_clauses(df,label,min_signals)
    res=list(unary)
    for i in range(len(clauses)):
        for j in range(i+1,len(clauses)):
            a,b=clauses[i],clauses[j]
            if a[0]==b[0]: continue
            mask=a[3] & b[3]
            rule=a[4]['rule']+' AND '+b[4]['rule']
            r=eval_mask(df,mask,label,rule)
            if r and r['signals']>=min_signals: res.append(r)
    # simple 3-clause from top 35 to keep interpretable
    top=clauses[:35]
    for a,b,c in itertools.combinations(top,3):
        if len({a[0],b[0],c[0]})<3: continue
        mask=a[3]&b[3]&c[3]
        rule=a[4]['rule']+' AND '+b[4]['rule']+' AND '+c[4]['rule']
        r=eval_mask(df,mask,label,rule)
        if r and r['signals']>=min_signals: res.append(r)
    res=sorted(res,key=lambda r:(r['hit_rate'],r['hits'],r['signals'],r['avg_np'],-r['max_dd']),reverse=True)
    seen=set(); out=[]
    for r in res:
        key=(tuple(r['starts']),r['rule'])
        startkey=tuple(r['starts'])
        # keep at most one rule per selected set in top list
        if startkey in seen: continue
        seen.add(startkey); out.append(r)
        if len(out)>=40: break
    return out


def main():
    rows=load_rows(); data=get_data(rows); df=make_features(rows,data)
    result={'total_windows':len(df),'label_counts':{k:int(df[k].sum()) for k in ['pass_any','pass_fast15','pass_fast10']}}
    for label,minsig in [('pass_fast15',3),('pass_fast15',4),('pass_fast15',5),('pass_any',5),('pass_any',7),('pass_any',8)]:
        result[f'{label}_min{minsig}']=search(df,label,minsig)[:20]
    OUT_JSON.write_text(json.dumps(result,indent=2),encoding='utf-8')
    lines=['PHASE47 NORMALIZED REGIME GATE RESEARCH',f'total_windows={result["total_windows"]} labels={result["label_counts"]}',f'features_csv={FEATURE_CSV}']
    for k,v in result.items():
        if not isinstance(v,list): continue
        lines.append('\n'+k)
        for r in v[:10]:
            lines.append(f"signals={r['signals']} hits={r['hits']} rate={r['hit_rate']} avg_np={r['avg_np']} min_np={r['min_np']} maxdd={r['max_dd']} fast15={r['fast15_hits']} any={r['any_hits']} rule={r['rule']}")
            lines.append(f"  starts={r['starts']} days={r['days']}")
    OUT_TXT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(OUT_TXT)

if __name__=='__main__': main()

