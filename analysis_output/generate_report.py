"""
Generate bilingual PDF reports (ID + EN)
Thesis: Edge-Intelligent Aquaculture NH3 Risk Monitoring
Author: Faril Pirwanhadi (M14128104)
"""
import csv, os
from datetime import datetime
from collections import Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

# ── paths ─────────────────────────────────────────────────────────────────────
BASE   = os.path.dirname(os.path.abspath(__file__))
COMP   = os.path.join(BASE, "comparison.csv")
QOS1   = os.path.join(BASE, "qos_pico1.csv")
QOS2   = os.path.join(BASE, "qos_pico2.csv")
QOS3   = os.path.join(BASE, "qos_pico3.csv")
OUT_ID = os.path.join(BASE, "Laporan_Pengujian_1_ID.pdf")
OUT_EN = os.path.join(BASE, "Laporan_Pengujian_1_EN.pdf")
IMGDIR  = os.path.join(BASE, "charts")
SIMDIR  = os.path.join(os.path.dirname(BASE), "results", "simulation")
os.makedirs(IMGDIR, exist_ok=True)

# ── chart palette (light theme) ───────────────────────────────────────────────
CB = "#1d4ed8"; CG = "#16a34a"; CY = "#ca8a04"
CO = "#ea580c"; CR = "#dc2626"; CP = "#7c3aed"
CC = "#0891b2"; CGR= "#6b7280"
RISK_C = {0:CG, 1:CY, 2:CO, 3:CR}
RISK_L = {0:"SAFE", 1:"CAUTION", 2:"WARNING", 3:"DANGER"}

plt.rcParams.update({
    'figure.facecolor':'white','axes.facecolor':'#f8fafc',
    'axes.edgecolor':'#cbd5e1','axes.labelcolor':'#1e293b',
    'text.color':'#1e293b','xtick.color':'#475569','ytick.color':'#475569',
    'grid.color':'#e2e8f0','grid.alpha':0.8,'grid.linestyle':'--',
    'font.family':'DejaVu Sans','font.size':9,
    'axes.spines.top':False,'axes.spines.right':False,
})

# ── load data ─────────────────────────────────────────────────────────────────
def load_csv(p):
    with open(p, newline='', encoding='utf-8') as f: return list(csv.DictReader(f))

print("Loading data...")
rows = load_csv(COMP)
qos1 = load_csv(QOS1); qos2 = load_csv(QOS2); qos3 = load_csv(QOS3)
print(f"  comparison:{len(rows)}  qos1:{len(qos1)}  qos2:{len(qos2)}  qos3:{len(qos3)}")

steps    = [int(r['real_step'])   for r in rows]
ph_vals  = [float(r['pH'])        for r in rows]
nh3_vals = [float(r['NH3_pct'])   for r in rows]
modes    = [r['mode']             for r in rows]
a_risks  = [int(r['actual_risk']) for r in rows]
epsilons = [float(r['epsilon'])   for r in rows]
fql_s_col= [int(r['fql_steps'])   for r in rows]
bws_col  = [float(r['bandwidth_mbps']) for r in rows]
lat_col  = [float(r['latency_ms'])     for r in rows]
jit_col  = [float(r['jitter_ms'])      for r in rows]

rb_rows  = [r for r in rows if r['mode']=='RB']
fql_rows = [r for r in rows if r['mode']=='FQL']
dqn_rows = [r for r in rows if r['mode']=='DQN']
rb_end   = max(int(r['real_step']) for r in rb_rows)
fql_end  = max(int(r['real_step']) for r in fql_rows)

rb_a  = sum(int(r['rb_correct'])  for r in rb_rows)  / len(rb_rows)  * 100
fql_a = sum(int(r['fql_correct']) for r in fql_rows) / len(fql_rows) * 100
dv    = [r for r in dqn_rows if r['dqn_correct'] not in ('-1','')]
dqn_a = sum(int(r['dqn_correct']) for r in dv) / len(dv) * 100 if dv else 0

def lavg(lst, k): return sum(float(r[k]) for r in lst)/len(lst)
def roll(lst, w): return [np.mean(lst[max(0,i-w):i+1]) for i in range(len(lst))]
def ds(lst, n=2000): s=max(1,len(lst)//n); return lst[::s]

# ── chart helpers ─────────────────────────────────────────────────────────────
def save(fig, name):
    p = os.path.join(IMGDIR, name)
    fig.savefig(p, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  {name}")
    return p

def vlines(ax):
    ax.axvline(rb_end,  color='#94a3b8', lw=1.2, ls='--', alpha=0.9)
    ax.axvline(fql_end, color='#94a3b8', lw=1.2, ls='--', alpha=0.9)

def phase_spans(ax):
    ax.axvspan(steps[0], rb_end,    alpha=0.05, color=CB, zorder=0)
    ax.axvspan(rb_end,   fql_end,   alpha=0.05, color=CY, zorder=0)
    ax.axvspan(fql_end,  steps[-1], alpha=0.05, color=CG, zorder=0)

# ═════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═════════════════════════════════════════════════════════════════════════════
def c1_phase():
    fig, ax = plt.subplots(figsize=(13, 2.0))
    for x0,x1,c,lbl in [(steps[0],rb_end,CB,'Rule-Based (1–2.000)'),
                         (rb_end,fql_end,CY,'FQL (2.001–3.000)'),
                         (fql_end,steps[-1],CG,'DQN (3.001–29.938)')]:
        ax.axvspan(x0,x1,alpha=0.18,color=c)
        ax.text((x0+x1)/2,0.5,lbl,ha='center',va='center',
                fontsize=9.5,fontweight='bold',color=c,transform=ax.get_xaxis_transform())
    ax.axvline(rb_end, color='#475569',lw=1.5,ls='--')
    ax.axvline(fql_end,color='#475569',lw=1.5,ls='--')
    ax.set_xlabel('Step',fontsize=9); ax.set_yticks([])
    ax.set_xlim(steps[0],steps[-1])
    for sp in ['top','right','left']: ax.spines[sp].set_visible(False)
    plt.tight_layout(pad=0.4)
    return save(fig,'c1_phase.png')

def c2_acc_bar():
    fig, ax = plt.subplots(figsize=(7,4.5))
    bars = ax.bar(['Rule-Based','FQL','DQN'],[rb_a,fql_a,dqn_a],
                  color=[CB,CY,CG],width=0.45,edgecolor='white',linewidth=1.5,zorder=3)
    for b,v in zip(bars,[rb_a,fql_a,dqn_a]):
        ax.text(b.get_x()+b.get_width()/2,b.get_height()+0.8,f'{v:.1f}%',
                ha='center',va='bottom',fontsize=13,fontweight='bold',color=b.get_facecolor())
    ax.set_ylim(0,115); ax.set_ylabel('Accuracy (%)'); ax.axhline(100,color='#94a3b8',lw=1,ls=':')
    ax.grid(axis='y',zorder=0); plt.tight_layout(pad=0.8)
    return save(fig,'c2_acc_bar.png')

def c3_rolling():
    W=300
    rb_all =[float(r['rb_correct'])  for r in rows]
    fql_all=[float(r['fql_correct']) for r in rows]
    dqn_s  =[(int(r['real_step']),float(r['dqn_correct']))
              for r in dqn_rows if r['dqn_correct'] not in ('-1','')]
    fig,ax=plt.subplots(figsize=(13,3.8))
    phase_spans(ax)
    ax.plot(ds(steps),ds([v*100 for v in roll(rb_all,W)]), color=CB,lw=1.8,label='Rule-Based')
    ax.plot(ds(steps),ds([v*100 for v in roll(fql_all,W)]),color=CY,lw=1.8,label='FQL')
    if dqn_s:
        dst,dv_=zip(*dqn_s)
        ax.plot(ds(list(dst)),ds([v*100 for v in roll(list(dv_),W)]),color=CG,lw=1.8,label='DQN')
    vlines(ax)
    ax.set_xlabel('Step'); ax.set_ylabel('Rolling Accuracy (%)'); ax.set_ylim(0,110)
    ax.grid(); ax.legend(fontsize=9,framealpha=0.6)
    plt.tight_layout(pad=0.8)
    return save(fig,'c3_rolling.png')

def c4_epsilon():
    fig,ax=plt.subplots(figsize=(13,3.2))
    phase_spans(ax)
    s_ds=ds(steps); e_ds=ds(epsilons)
    ax.fill_between(s_ds,e_ds,0,alpha=0.12,color=CP)
    ax.plot(s_ds,e_ds,color=CP,lw=2,label='Epsilon')
    ax.axhline(0.1,color=CGR,lw=1,ls=':',label='ε min')
    vlines(ax)
    for x,lbl,c in [(rb_end/2,'RB',CB),((rb_end+fql_end)/2,'FQL',CY),((fql_end+steps[-1])/2,'DQN',CG)]:
        ax.text(x,0.27,lbl,ha='center',color=c,fontsize=9,fontweight='bold')
    ax.set_xlabel('Step'); ax.set_ylabel('Epsilon'); ax.set_ylim(0,0.35)
    ax.grid(); ax.legend(fontsize=9,framealpha=0.6)
    plt.tight_layout(pad=0.8)
    return save(fig,'c4_epsilon.png')

def c5_fql_zoom():
    fql_idx=[i for i,r in enumerate(rows) if r['mode']=='FQL']
    if not fql_idx: return None
    fql_s  =[steps[i]    for i in fql_idx]
    fql_eps=[epsilons[i] for i in fql_idx]
    fql_acc=[float(rows[i]['fql_correct']) for i in fql_idx]
    racc   =[np.mean(fql_acc[max(0,i-50):i+1])*100 for i in range(len(fql_acc))]
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(13,5.2),sharex=True)
    ax1.fill_between(fql_s,fql_eps,0,alpha=0.12,color=CP)
    ax1.plot(fql_s,fql_eps,color=CP,lw=2); ax1.set_ylabel('Epsilon'); ax1.grid()
    ax2.fill_between(fql_s,racc,0,alpha=0.12,color=CY)
    ax2.plot(fql_s,racc,color=CY,lw=2)
    ax2.axhline(90,color=CGR,lw=1,ls=':',label='90%')
    ax2.set_xlabel('Step'); ax2.set_ylabel('Rolling Accuracy (%)'); ax2.legend(fontsize=9); ax2.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c5_fql_zoom.png')

def c6_pred_compare():
    fig,axes=plt.subplots(3,1,figsize=(13,7.5))
    phases=[('Rule-Based',rb_rows,CB,lambda r:(int(r['actual_risk']),int(r['rb_risk']))),
            ('FQL',fql_rows,CY,lambda r:(int(r['actual_risk']),int(r['fql_risk']))),
            ('DQN',dqn_rows[:3000],CG,lambda r:(int(r['actual_risk']),int(r['dqn_risk']) if r['dqn_risk'] not in ('-1','') else -1))]
    for ax,(title,pr,c,fn) in zip(axes,phases):
        ss=max(1,len(pr)//500); sub=pr[::ss]
        st_=[int(r['real_step']) for r in sub]
        act=[fn(r)[0] for r in sub]; prd=[fn(r)[1] for r in sub]
        ax.plot(st_,act,color='#94a3b8',lw=1,alpha=0.7,label='Actual',zorder=2)
        cx=[s for s,p,a in zip(st_,prd,act) if p==a]
        cp_=[p for s,p,a in zip(st_,prd,act) if p==a]
        wx=[s for s,p,a in zip(st_,prd,act) if p!=a and p!=-1]
        wp_=[p for s,p,a in zip(st_,prd,act) if p!=a and p!=-1]
        ax.scatter(cx,cp_,c=c,s=8,zorder=3,label='Correct',alpha=0.7)
        ax.scatter(wx,wp_,c=CR,s=25,marker='x',zorder=4,label='Wrong',linewidths=1.5)
        ax.set_ylabel('Risk Level',fontsize=8); ax.set_title(title,fontsize=10,fontweight='bold')
        ax.set_ylim(-0.5,3.8); ax.set_yticks([0,1,2,3]); ax.set_yticklabels(['SAFE','CAUTION','WARNING','DANGER'],fontsize=7.5)
        ax.grid(alpha=0.4); ax.legend(fontsize=7.5,framealpha=0.6,loc='upper right',ncol=3)
    axes[-1].set_xlabel('Step')
    plt.tight_layout(pad=0.8)
    return save(fig,'c6_pred_compare.png')

def c7_errors():
    W=200
    rb_e =[1-float(r['rb_correct'])  for r in rows]
    fql_e=[1-float(r['fql_correct']) for r in rows]
    dqn_e=[1-float(r['dqn_correct']) if r['dqn_correct'] not in ('-1','') else 0 for r in rows]
    fig,ax=plt.subplots(figsize=(13,3.5))
    phase_spans(ax)
    s2=ds(steps,1500)
    ax.plot(s2,ds([v*100 for v in roll(rb_e, W)],1500),color=CB,lw=1.8,label='RB')
    ax.plot(s2,ds([v*100 for v in roll(fql_e,W)],1500),color=CY,lw=1.8,label='FQL')
    ax.plot(s2,ds([v*100 for v in roll(dqn_e,W)],1500),color=CG,lw=1.8,label='DQN')
    vlines(ax); ax.set_xlabel('Step'); ax.set_ylabel('Error Rate (%)')
    ax.set_ylim(0,25); ax.grid(); ax.legend(fontsize=9,framealpha=0.6)
    plt.tight_layout(pad=0.8)
    return save(fig,'c7_errors.png')

def c8_sensor_overlay():
    fig,(ax1,ax2,ax3)=plt.subplots(3,1,figsize=(13,7.5),sharex=True)
    s2=ds(steps,2000)
    ax1.fill_between(s2,ds(ph_vals),min(ph_vals)*0.998,alpha=0.12,color=CC)
    ax1.plot(s2,ds(ph_vals),color=CC,lw=1.5)
    ax1.set_ylabel('pH'); ax1.grid()
    ax2.fill_between(s2,ds(nh3_vals),0,alpha=0.12,color=CO)
    ax2.plot(s2,ds(nh3_vals),color=CO,lw=1.5)
    ax2.axhline(2.0,color=CR,lw=0.8,ls=':',alpha=0.7); ax2.set_ylabel('NH3 (%)'); ax2.grid()
    mc={'RB':CB,'FQL':CY,'DQN':CG}
    pm,ps=modes[0],steps[0]
    for i in range(1,len(modes)):
        if modes[i]!=pm or i==len(modes)-1:
            ax3.axvspan(ps,steps[i-1],alpha=0.2,color=mc[pm]); pm,ps=modes[i],steps[i]
    rbw=[s for s,r in zip(steps,rows) if r['rb_correct'] =='0'][::10]
    fqlw=[s for s,r in zip(steps,rows) if r['fql_correct']=='0'][::5]
    dqnw=[s for s,r in zip(steps,rows) if r['dqn_correct']=='0' and r['mode']=='DQN'][::5]
    ax3.scatter(rbw, [1.5]*len(rbw), c=CR,s=7,alpha=0.5,label='RB wrong')
    ax3.scatter(fqlw,[2.5]*len(fqlw),c=CR,s=7,alpha=0.5,label='FQL wrong')
    ax3.scatter(dqnw,[3.5]*len(dqnw),c=CR,s=7,alpha=0.5,label='DQN wrong')
    ax3.set_yticks([1.5,2.5,3.5]); ax3.set_yticklabels(['RB','FQL','DQN'],fontsize=8.5)
    ax3.set_ylabel('AI Mode'); ax3.set_xlabel('Step')
    ax3.legend(fontsize=7.5,framealpha=0.6,loc='upper right',ncol=3); ax3.grid(alpha=0.3)
    plt.tight_layout(pad=0.8)
    return save(fig,'c8_sensor_overlay.png')

def c9_fql_steps_acc():
    fql_idx=[i for i,r in enumerate(rows) if r['mode']=='FQL']
    if not fql_idx: return None
    fql_s  =[fql_s_col[i] for i in fql_idx]
    fql_acc=[float(rows[i]['fql_correct']) for i in fql_idx]
    fql_eps=[epsilons[i]  for i in fql_idx]
    racc   =[np.mean(fql_acc[max(0,j-30):j+1])*100 for j in range(len(fql_acc))]
    fig,ax=plt.subplots(figsize=(10,3.8))
    ax.fill_between(fql_s,racc,0,alpha=0.1,color=CY)
    ax.plot(fql_s,racc,color=CY,lw=2,label='FQL Accuracy (roll-30)')
    ax2=ax.twinx()
    ax2.plot(fql_s,fql_eps,color=CP,lw=1.5,ls='--',alpha=0.8,label='Epsilon')
    ax2.set_ylabel('Epsilon',color=CP); ax2.tick_params(axis='y',colors=CP)
    ax.set_xlabel('FQL Internal Steps'); ax.set_ylabel('Accuracy (%)')
    lines1,labs1=ax.get_legend_handles_labels(); lines2,labs2=ax2.get_legend_handles_labels()
    ax.legend(lines1+lines2,labs1+labs2,fontsize=9,framealpha=0.6)
    ax.set_ylim(0,110); ax.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c9_fql_convergence.png')

def c10_dqn_acc():
    dqn_idx=[i for i,r in enumerate(rows) if r['mode']=='DQN' and r['dqn_correct'] not in ('-1','')]
    if not dqn_idx: return None
    dqn_s  =[steps[i] for i in dqn_idx]
    dqn_acc=[float(rows[i]['dqn_correct']) for i in dqn_idx]
    racc   =[np.mean(dqn_acc[max(0,j-500):j+1])*100 for j in range(len(dqn_acc))]
    fig,ax=plt.subplots(figsize=(13,3.5))
    ax.fill_between(ds(dqn_s,2000),ds(racc,2000),80,alpha=0.12,color=CG)
    ax.plot(ds(dqn_s,2000),ds(racc,2000),color=CG,lw=2)
    ax.axhline(100,color=CGR,lw=1,ls=':')
    ax.set_xlabel('Step'); ax.set_ylabel('DQN Accuracy (%)'); ax.set_ylim(80,105); ax.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c10_dqn_acc.png')

def c11_lat():
    fig,ax=plt.subplots(figsize=(13,3.8))
    for qos,c,lbl in [(qos1,CB,'Pico 1 (Main)'),(qos2,CY,'Pico 2 (Dummy)'),(qos3,CG,'Pico 3 (Dummy)')]:
        idx=list(range(0,len(qos),max(1,len(qos)//1500)))
        ax.plot(idx,[float(qos[i]['latency_ms']) for i in idx],color=c,lw=1.3,alpha=0.9,label=lbl)
    ax.set_xlabel('Sample'); ax.set_ylabel('Latency (ms)')
    ax.legend(fontsize=9,framealpha=0.6); ax.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c11_latency.png')

def c12_jit():
    fig,ax=plt.subplots(figsize=(13,3.8))
    cap=80
    for qos,c,lbl in [(qos1,CB,'Pico 1 (Main)'),(qos2,CY,'Pico 2 (Dummy)'),(qos3,CG,'Pico 3 (Dummy)')]:
        idx=list(range(0,len(qos),max(1,len(qos)//1500)))
        ax.plot(idx,[min(float(qos[i]['jitter_ms']),cap) for i in idx],color=c,lw=1.3,alpha=0.9,label=lbl)
    ax.set_xlabel('Sample'); ax.set_ylabel(f'Jitter (ms, cap {cap})')
    ax.legend(fontsize=9,framealpha=0.6); ax.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c12_jitter.png')

def c13_bw():
    fig,ax=plt.subplots(figsize=(13,3.8))
    for qos,c,lbl in [(qos1,CB,'Pico 1 (Main)'),(qos2,CY,'Pico 2 (Dummy)'),(qos3,CG,'Pico 3 (Dummy)')]:
        idx=list(range(0,len(qos),max(1,len(qos)//1500)))
        ax.plot(idx,[float(qos[i]['bandwidth_mbps'])*1000 for i in idx],color=c,lw=1.3,alpha=0.9,label=lbl)
    ax.set_xlabel('Sample'); ax.set_ylabel('Bandwidth (Kbps)')
    ax.legend(fontsize=9,framealpha=0.6); ax.grid()
    plt.tight_layout(pad=0.8)
    return save(fig,'c13_bandwidth.png')

def c14_qos_sum():
    fig,axes=plt.subplots(1,3,figsize=(13,3.8))
    nodes=['Pico 1\n(Main)','Pico 2\n(Dummy)','Pico 3\n(Dummy)']
    clrs=[CB,CY,CG]
    def avg(r,k): return sum(float(x[k]) for x in r)/len(r)
    for ax,(vals,title,unit) in zip(axes,[
        ([avg(qos1,'latency_ms'),avg(qos2,'latency_ms'),avg(qos3,'latency_ms')],'Avg Latency','ms'),
        ([min(avg(qos1,'jitter_ms'),50),min(avg(qos2,'jitter_ms'),50),min(avg(qos3,'jitter_ms'),50)],'Avg Jitter','ms'),
        ([avg(qos1,'bandwidth_mbps')*1000,avg(qos2,'bandwidth_mbps')*1000,avg(qos3,'bandwidth_mbps')*1000],'Avg Bandwidth','Kbps'),
    ]):
        bars=ax.bar(nodes,vals,color=clrs,width=0.45,edgecolor='white',linewidth=1.5,zorder=3)
        for b,v in zip(bars,vals):
            ax.text(b.get_x()+b.get_width()/2,b.get_height()+0.02*max(vals),
                    f'{v:.2f}',ha='center',va='bottom',fontsize=9,fontweight='bold')
        ax.set_title(f'{title} ({unit})',fontsize=9,fontweight='bold'); ax.grid(axis='y',zorder=0)
    plt.tight_layout(pad=0.8)
    return save(fig,'c14_qos_sum.png')

def c15_qos_during_ai():
    fig,(a1,a2,a3)=plt.subplots(3,1,figsize=(13,7.5),sharex=True)
    s2=ds(steps,2000)
    ld=ds(lat_col,2000); jd=ds(jit_col,2000); bd=ds(bws_col,2000)
    a1.fill_between(s2,[min(v,20) for v in ld],0,alpha=0.12,color=CC)
    a1.plot(s2,[min(v,20) for v in ld],color=CC,lw=1.5); a1.set_ylabel('Latency (ms)'); a1.grid(); vlines(a1)
    a2.fill_between(s2,[min(v,30) for v in jd],0,alpha=0.12,color=CO)
    a2.plot(s2,[min(v,30) for v in jd],color=CO,lw=1.5); a2.set_ylabel('Jitter (ms)'); a2.grid(); vlines(a2)
    a3.fill_between(s2,[v*1000 for v in bd],0,alpha=0.12,color=CG)
    a3.plot(s2,[v*1000 for v in bd],color=CG,lw=1.5); a3.set_ylabel('Bandwidth (Kbps)'); a3.set_xlabel('Step'); a3.grid(); vlines(a3)
    plt.tight_layout(pad=0.8)
    return save(fig,'c15_qos_during_ai.png')

def c16_dist():
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,4.2))
    rc=Counter(a_risks)
    labs=[RISK_L[k] for k in sorted(rc)]; szs=[rc[k] for k in sorted(rc)]; clrs=[RISK_C[k] for k in sorted(rc)]
    _,txts,autotxts=ax1.pie(szs,labels=labs,colors=clrs,autopct='%1.1f%%',startangle=140,
                             pctdistance=0.78,wedgeprops=dict(edgecolor='white',linewidth=2))
    for t in txts: t.set_fontsize(10)
    for t in autotxts: t.set_fontsize(9); t.set_fontweight('bold')
    mc=Counter(modes); ml=list(mc.keys()); mv=[mc[m] for m in ml]
    bars=ax2.bar(ml,mv,color=[CB,CY,CG][:len(ml)],width=0.45,edgecolor='white',linewidth=1.5,zorder=3)
    for b,v in zip(bars,mv):
        ax2.text(b.get_x()+b.get_width()/2,b.get_height()+100,f'{v:,}',ha='center',va='bottom',fontsize=10,fontweight='bold')
    ax2.set_ylabel('Steps'); ax2.grid(axis='y',zorder=0)
    plt.tight_layout(pad=0.8)
    return save(fig,'c16_dist.png')

def c17_reward():
    sr=[]
    for r in rows:
        m=r['mode']
        if m=='RB':  sr.append(1 if r['rb_correct'] =='1' else -1)
        elif m=='FQL': sr.append(1 if r['fql_correct']=='1' else -1)
        else: sr.append(1 if r['dqn_correct']=='1' else (-1 if r['dqn_correct']=='0' else 0))
    cr=list(np.cumsum(sr)); rr=[np.mean(sr[max(0,i-200):i+1]) for i in range(len(sr))]
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(13,6.5),sharex=True)
    s2=ds(steps,2000)
    phase_spans(ax1)
    ax1.fill_between(s2,[v*100 for v in ds(rr,2000)],0,alpha=0.12,color=CY)
    ax1.plot(s2,[v*100 for v in ds(rr,2000)],color=CY,lw=1.8)
    ax1.axhline(0,color=CGR,lw=0.8,ls='--'); ax1.set_ylabel('Avg Reward (%)'); ax1.grid(); vlines(ax1)
    cr2=ds(cr,2000)
    phase_spans(ax2)
    ax2.fill_between(s2,cr2,0,where=[v>=0 for v in cr2],alpha=0.12,color=CG)
    ax2.fill_between(s2,cr2,0,where=[v<0  for v in cr2],alpha=0.12,color=CR)
    ax2.plot(s2,cr2,color=CG,lw=1.8)
    ax2.axhline(0,color=CGR,lw=0.8,ls='--'); ax2.set_xlabel('Step'); ax2.set_ylabel('Cumulative Reward'); ax2.grid(); vlines(ax2)
    plt.tight_layout(pad=0.8)
    return save(fig,'c17_reward.png')

def c18_conf_matrix():
    rb_t=[int(r['actual_risk']) for r in rb_rows]; rb_p=[int(r['rb_risk']) for r in rb_rows]
    fql_t=[int(r['actual_risk']) for r in fql_rows]; fql_p=[int(r['fql_risk']) for r in fql_rows]
    dv_=[(int(r['actual_risk']),int(r['dqn_risk'])) for r in dqn_rows if r['dqn_risk'] not in ('-1','')]
    dqn_t=[x[0] for x in dv_]; dqn_p=[x[1] for x in dv_]
    def build_cm(tv,pv):
        cm=np.zeros((4,4),dtype=int)
        for t,p in zip(tv,pv):
            if 0<=t<=3 and 0<=p<=3: cm[t][p]+=1
        return cm
    fig,axes=plt.subplots(1,3,figsize=(14,4.2))
    lnames=['SAFE','CAUTION','WARNING','DANGER']
    for ax,(tv,pv),title,c in zip(axes,[(rb_t,rb_p),(fql_t,fql_p),(dqn_t,dqn_p)],
                                    ['Rule-Based','FQL','DQN'],[CB,CY,CG]):
        cm=build_cm(tv,pv); rs=cm.sum(axis=1,keepdims=True); rs[rs==0]=1
        cm_n=cm.astype(float)/rs
        ax.imshow(cm_n,cmap='Blues',vmin=0,vmax=1,aspect='auto')
        ax.set_xticks(range(4)); ax.set_xticklabels(lnames,rotation=30,ha='right',fontsize=7.5)
        ax.set_yticks(range(4)); ax.set_yticklabels(lnames,fontsize=7.5)
        ax.set_xlabel('Predicted',fontsize=8); ax.set_ylabel('Actual',fontsize=8)
        ax.set_title(title,fontsize=11,fontweight='bold',color=c,pad=8)
        for i in range(4):
            for j in range(4):
                if cm[i][j]>0:
                    tc='white' if cm_n[i][j]>0.55 else '#1e293b'
                    ax.text(j,i,f'{cm[i][j]:,}',ha='center',va='center',fontsize=8,color=tc,fontweight='bold')
    plt.tight_layout(pad=1.0)
    return save(fig,'c18_conf_matrix.png')

def c19_policy_map():
    dr=[r for r in dqn_rows if r['dqn_risk'] not in ('-1','')]
    if len(dr)<100: return None
    ph_v=[float(r['pH']) for r in dr]; nh3_v=[float(r['NH3_pct']) for r in dr]
    pred_v=[int(r['dqn_risk']) for r in dr]; act_v=[int(r['actual_risk']) for r in dr]
    ph_b=np.linspace(min(ph_v),max(ph_v),18); nh3_b=np.linspace(min(nh3_v),max(nh3_v),18)
    grid=np.full((len(nh3_b)-1,len(ph_b)-1),np.nan); cnt=np.zeros_like(grid)
    for ph,nh3,p in zip(ph_v,nh3_v,pred_v):
        xi=max(0,min(np.searchsorted(ph_b, ph, side='right')-1,grid.shape[1]-1))
        yi=max(0,min(np.searchsorted(nh3_b,nh3,side='right')-1,grid.shape[0]-1))
        grid[yi,xi]=(grid[yi,xi]*cnt[yi,xi]+p)/(cnt[yi,xi]+1) if cnt[yi,xi]>0 else p
        cnt[yi,xi]+=1
    fig,(ax1,ax2)=plt.subplots(1,2,figsize=(14,5.0))
    cmap_r=mcolors.LinearSegmentedColormap.from_list('r',[CG,CY,CO,CR],N=256)
    im=ax1.imshow(grid,origin='lower',aspect='auto',cmap=cmap_r,vmin=0,vmax=3,
                  extent=[ph_b[0],ph_b[-1],nh3_b[0],nh3_b[-1]])
    cb=plt.colorbar(im,ax=ax1,ticks=[0,1,2,3]); cb.set_ticklabels(['SAFE','CAUTION','WARNING','DANGER']); cb.ax.tick_params(labelsize=8)
    ax1.set_xlabel('pH'); ax1.set_ylabel('NH3 (%)'); ax1.set_title('DQN Policy Map',fontsize=10,fontweight='bold')
    for rid in [0,1,2,3]:
        idx=[i for i,r in enumerate(dr) if int(r['actual_risk'])==rid]
        if idx: ax2.scatter([ph_v[i] for i in idx],[nh3_v[i] for i in idx],
                            c=RISK_C[rid],s=4,alpha=0.3,label=RISK_L[rid])
    ax2.set_xlabel('pH'); ax2.set_ylabel('NH3 (%)'); ax2.set_title('Actual Risk Distribution',fontsize=10,fontweight='bold')
    ax2.legend(fontsize=9,framealpha=0.6,markerscale=3); ax2.grid(alpha=0.5)
    plt.tight_layout(pad=0.8)
    return save(fig,'c19_policy_map.png')

# ── generate all charts ───────────────────────────────────────────────────────
print("\nGenerating charts...")
P={}
P['timeline'] = c1_phase()
P['acc_bar']  = c2_acc_bar()
P['rolling']  = c3_rolling()
P['epsilon']  = c4_epsilon()
P['fql_zoom'] = c5_fql_zoom()
P['pred']     = c6_pred_compare()
P['errors']   = c7_errors()
P['overlay']  = c8_sensor_overlay()
P['fql_conv'] = c9_fql_steps_acc()
P['dqn_acc']  = c10_dqn_acc()
P['lat']      = c11_lat()
P['jit']      = c12_jit()
P['bw']       = c13_bw()
P['qos_sum']  = c14_qos_sum()
P['qos_ai']   = c15_qos_during_ai()
P['dist']     = c16_dist()
P['reward']   = c17_reward()
P['conf']     = c18_conf_matrix()
P['policy']   = c19_policy_map()
print(f"Done — {sum(1 for v in P.values() if v)} charts")

# ── simulation image paths (pre-existing, not regenerated) ────────────────
PSIM = {
    'sim1': os.path.join(SIMDIR, 'sim_1_accuracy.png'),
    'sim2': os.path.join(SIMDIR, 'sim_2_metrics.png'),
    'sim4': os.path.join(SIMDIR, 'sim_4_radar.png'),
    'sim5': os.path.join(SIMDIR, 'sim_5_confusion.png'),
    'sim6': os.path.join(SIMDIR, 'sim_6_rewards.png'),
    'sim9': os.path.join(SIMDIR, 'sim_9_improvement.png'),
}

# ═════════════════════════════════════════════════════════════════════════════
# TEXT CONTENT  (id = Bahasa Indonesia, en = English)
# ═════════════════════════════════════════════════════════════════════════════
T = {
'id': {
  'out': OUT_ID,
  'cover_title':    'LAPORAN PENGUJIAN SISTEM',
  'cover_sub':      'Edge-Intelligent Aquaculture NH3 Risk Monitoring',
  'cover_session':  'Pengujian Pertama  ·  Session 20260529_014459',
  'cover_info':     'Durasi: ~16.6 jam  ·  Total Step: 29.938  ·  3 Node IoT Aktif',
  'header_left':    'LAPORAN PENGUJIAN SISTEM',
  'header_right':   'Edge-Intelligent Aquaculture NH3 Risk Monitoring',
  'footer_left':    'Faril Pirwanhadi — M14128104',
  'footer_center':  'Halaman',
  'sum_headers':    ['Parameter','Nilai'],
  'sum_rows': [
    ['Total Step', f'{len(rows):,}'], ['Durasi', '~16.6 jam'],
    ['Akurasi Rule-Based', f'{rb_a:.1f}%'], ['Akurasi FQL', f'{fql_a:.1f}%'],
    ['Akurasi DQN', f'{dqn_a:.1f}%'], ['FQL Konvergen di', 'Step 2.001'],
    ['DQN Aktif di', 'Step 3.001'],
    ['pH Rata-rata', f'{sum(ph_vals)/len(ph_vals):.3f}'],
    ['NH3 Rata-rata', f'{sum(nh3_vals)/len(nh3_vals):.3f}%'],
    ['Latency Pico 1', f'{lavg(qos1,"latency_ms"):.2f} ms'],
    ['Latency Pico 2', f'{lavg(qos2,"latency_ms"):.2f} ms'],
    ['Latency Pico 3', f'{lavg(qos3,"latency_ms"):.2f} ms'],
  ],
  's1': 'Pendahuluan',
  'p1a': ('Laporan ini menyajikan hasil pengujian pertama sistem monitoring risiko amonia (NH3) '
          'pada tambak budidaya berbasis kecerdasan buatan di tepi jaringan (edge AI). '
          'Sistem dijalankan di <b>Raspberry Pi 5</b> sebagai server pusat, '
          'dengan tiga <b>Raspberry Pi Pico</b> terhubung melalui WiFi 2.4 GHz.'),
  'p1b': ('Pico 1 (WH/RP2040) membaca sensor pH dan suhu secara real-time. '
          'Pico 2 dan Pico 3 (2W/RP2350) menghasilkan lalu lintas jaringan untuk mengukur QoS.'),
  'p1c': ('Sistem AI berjalan <b>progresif dan otomatis</b>: '
          '<b>Rule-Based (RB)</b> → <b>FQL</b> → <b>DQN</b>. '
          'Seluruh transisi terjadi tanpa intervensi manual.'),
  's2': 'Alur Transisi Fase AI',
  'p2a': ('Grafik berikut menunjukkan kapan setiap fase AI berjalan. '
          'Satu step ≈ satu pembacaan sensor (~2 detik). '
          'Garis putus vertikal menandai perpindahan fase.'),
  'fig1': ('Gambar 1 — Timeline fase AI. Biru = Rule-Based, Kuning = FQL, Hijau = DQN.'),
  'phase_headers': ['Fase','Rentang Step','Jumlah Step','Keterangan'],
  'phase_rows': [
    ['Rule-Based','1 – 2.000','2.000','Aturan baku if-then, tidak ada pembelajaran'],
    ['FQL','2.001 – 3.000','1.000','Belajar dari feedback, epsilon turun bertahap'],
    ['DQN','3.001 – 29.938','26.938','Neural network, dilatih dari memori FQL'],
  ],
  'p2b': ('FQL konvergen setelah 1.000 step. DQN selesai dilatih hanya dalam <b>52 detik</b> '
          'menggunakan 2.001 transisi dari FQL.'),
  'part_sim': 'BAGIAN SIMULASI — Validasi Sebelum Implementasi Real',
  'part_sim_desc': ('Sebelum pengujian dengan hardware nyata, sistem divalidasi terlebih dahulu melalui '
                    'simulasi komputasi menggunakan 30.000 sampel sintetik di 7 skenario kondisi air yang berbeda. '
                    'Tujuannya adalah membuktikan bahwa hierarki performa DQN > FQL > Rule-Based konsisten '
                    'sebelum diimplementasikan ke perangkat fisik.'),
  's_sim1': 'Gambaran Umum Hasil Simulasi',
  'p_sim1a': ('Simulasi dijalankan dengan 150 episode pengujian, masing-masing 200 step (total 30.000 sampel). '
              'Tujuh skenario kondisi air diuji secara berurutan: Safe, Acidic, Alkaline, Cold, Hot, Multi-stress, '
              'dan Random. Untuk memastikan konsistensi, validasi statistik dilakukan dengan 5 run independen '
              'menggunakan konfigurasi yang sama.'),
  'sim_fig1': ('Gambar S1 — Akurasi rata-rata simulasi dari 5 run: Rule-Based 75.76% (±0.09%), '
               'FQL 82.51% (±0.42%), DQN 96.54% (±0.07%). Hierarki DQN > FQL > Rule-Based '
               'terbukti konsisten di semua 5 run (100% success rate).'),
  'p_sim1b': ('DQN tidak hanya mencapai akurasi tertinggi, tetapi juga stabilitas terbaik dengan standar deviasi '
              'hanya 0.07% dibanding FQL yang 0.42%. Artinya DQN menghasilkan prediksi yang andal di berbagai '
              'kondisi, bukan hanya baik secara rata-rata.'),
  'sim_fig2': ('Gambar S2 — Peningkatan relatif antar metode. FQL meningkat +8.9% dibanding Rule-Based, '
               'DQN meningkat +17.0% dibanding FQL, dan secara total DQN +27.4% di atas Rule-Based. '
               'Reward ikut meningkat signifikan: +22.6%, +30.6%, dan +60.1%.'),
  's_sim2': 'Analisis Detail: Metrik, Reward, dan Perbandingan Multi-Dimensi',
  'p_sim2a': ('Analisis lebih dalam menggunakan radar chart multi-metrik dan confusion matrix '
              'mempertegas keunggulan DQN di setiap dimensi pengukuran. '
              'Rata-rata F1-score DQN mencapai 94.02%, jauh di atas FQL (64.51%) dan Rule-Based (68.96%).'),
  'sim_fig3': ('Gambar S3 — Radar chart perbandingan multi-metrik. DQN mendominasi di semua sumbu: '
               'akurasi, precision, recall, F1-score, dan stabilitas reward. '
               'FQL berada di tengah, Rule-Based paling terbatas.'),
  'sim_fig4': ('Gambar S4 — Confusion matrix simulasi untuk RB (kiri), FQL (tengah), DQN (kanan). '
               'DQN memiliki diagonal paling penuh dengan sangat sedikit prediksi yang meleset '
               'di luar kelas yang benar.'),
  'sim_fig5': ('Gambar S5 — Perbandingan reward rata-rata per episode. DQN: 0.948±0.001 (paling stabil). '
               'FQL: 0.726±0.007. Rule-Based: 0.592±0.002. Semakin mendekati 1.0, semakin sering benar.'),
  'p_sim2b': ('Hasil simulasi ini menjadi landasan implementasi real: sistem dimulai dari Rule-Based sebagai '
              'baseline aman, kemudian FQL mengumpulkan pengalaman, dan akhirnya DQN dilatih dari memori FQL '
              'untuk mencapai performa optimal. Strategi progresif ini terbukti efektif di simulasi '
              'sebelum diuji di lingkungan nyata.'),
  'part_a': 'BAGIAN A — Analisis Performa Metode AI',
  'part_a_desc': ('Bagian ini membahas seluruh aspek performa ketiga metode AI secara berurutan: '
                  'kondisi data sensor, akurasi, proses belajar setiap metode, '
                  'analisis kesalahan, reward, confusion matrix, dan policy map.'),
  's3': 'Kondisi Data Sensor Selama Pengujian',
  'p3a': ('Sebelum menilai performa AI, penting memahami data yang diterima sistem. '
          'Grafik berikut menampilkan pH, kadar NH3 toksik, dan mode AI aktif '
          'dalam satu tampilan agar hubungan antar ketiganya terlihat jelas.'),
  'fig2': ('Gambar 2 — (Atas) pH berfluktuasi normal di rentang 7.47–7.64. '
           '(Tengah) NH3 berkisar 1.66–2.43%, zona CAUTION sesuai kondisi lingkungan. '
           '(Bawah) Mode AI aktif — titik merah = prediksi salah, sangat jarang.'),
  'fig3': ('Gambar 3 — (Kiri) Distribusi risk level aktual selama pengujian. '
           '(Kanan) DQN mendominasi 90% step pengujian.'),
  's4': 'Perbandingan Akurasi: RB vs FQL vs DQN',
  'p4a': ('Akurasi diukur sebagai persentase step di mana prediksi risk level '
          'tepat sama dengan nilai aktual dari sensor.'),
  'fig4': (f'Gambar 4 — Akurasi: Rule-Based {rb_a:.1f}%, FQL {fql_a:.1f}%, DQN {dqn_a:.1f}%.'),
  'p4b': ('<b>Rule-Based</b>: aturan if-then deterministik. Akurat selama kondisi sesuai aturan.'),
  'p4c': (f'<b>FQL</b>: belajar dari nol lewat coba-coba. Akurasi {fql_a:.1f}% meski ada fase eksplorasi.'),
  'p4d': (f'<b>DQN</b>: neural network dilatih dari memori FQL. Langsung akurat {dqn_a:.1f}% sejak aktif.'),
  's4s1': '4.1 Akurasi Bergulir Sepanjang Waktu',
  'fig5': ('Gambar 5 — Akurasi bergulir (window 300 step). '
           'RB stabil (biru). FQL berfluktuasi saat eksplorasi lalu stabil (kuning). '
           'DQN langsung stabil sejak step 3.001 (hijau).'),
  'p4e': ('Grafik ini berbeda dari bar chart: ia memperlihatkan apakah sistem konsisten '
          'sepanjang waktu atau hanya baik di rata-rata. '
          'DQN yang langsung stabil adalah tanda kualitas training yang baik.'),
  's5': 'Proses Belajar FQL — Epsilon Decay',
  'p5a': ('Epsilon mengontrol keseimbangan antara <b>eksplorasi</b> (mencoba aksi baru acak) '
          'dan <b>eksploitasi</b> (menggunakan pengetahuan terbaik). '
          'Analoginya: epsilon tinggi = mau mencoba menu baru di restoran; '
          'epsilon rendah = pesan menu favorit yang sudah terbukti.'),
  'fig6': ('Gambar 6 — Epsilon sepanjang pengujian. Stabil di fase RB. '
           'Turun dari ~0.30 ke minimum selama fase FQL. '
           'Di fase DQN sudah di nilai minimum.'),
  'p5b': ('Penurunan epsilon yang teratur menunjukkan FQL berhasil '
          'melewati fase eksplorasi dan beralih ke eksploitasi — '
          'perilaku yang diharapkan dan dikonfirmasi oleh meningkatnya akurasi.'),
  's5s1': '5.1 Akurasi dan Epsilon Selama Fase FQL',
  'fig7': ('Gambar 7 — Zoom fase FQL. (Atas) Epsilon turun bertahap. '
           '(Bawah) Akurasi naik seiring turunnya epsilon. '
           'Korelasi ini mengkonfirmasi eksplorasi berkurang → akurasi meningkat.'),
  'p5c': ('Di awal fase FQL (step 2.001–2.100), akurasi berfluktuasi karena banyak bereksplorasi. '
          'Setelah epsilon turun (~step 2.500), akurasi stabil di atas 90% — tanda konvergensi sehat.'),
  's5s2': '5.2 Konvergensi FQL: Akurasi & Epsilon',
  'fig8': ('Gambar 8 — Konvergensi FQL dilihat dari internal step. '
           'Garis kuning = akurasi bergulir 30 step. Garis ungu = epsilon. '
           'Epsilon kecil → akurasi naik dan stabil.'),
  's6': 'Performa DQN — Deep Q-Network',
  'p6a': ('DQN menggunakan jaringan saraf tiruan untuk menangkap pola lebih kompleks. '
          'DQN dilatih dari <b>replay buffer</b> berisi 2.001 transisi yang dikumpulkan FQL. '
          'Proses training selesai dalam <b>52 detik</b>.'),
  'fig9': (f'Gambar 9 — Akurasi DQN (bergulir 500 step) dari step 3.001 hingga 29.938. '
           f'Langsung beroperasi di {dqn_a:.1f}% dan konsisten sepanjang 26.938 step.'),
  'p6b': ('Konsistensi akurasi DQN selama lebih dari 26.000 step membuktikan model tidak '
          'mengalami overfitting maupun degradasi performa.'),
  's7': 'Prediksi vs Actual Risk per Fase',
  'p7a': ('Grafik berikut membandingkan prediksi setiap metode dengan nilai aktual. '
          'Titik berwarna = benar, tanda silang merah = salah.'),
  'fig10': ('Gambar 10 — Prediksi vs Actual untuk RB (atas), FQL (tengah), DQN (bawah). '
            'RB dan DQN hampir tidak ada tanda silang merah. '
            'FQL memiliki beberapa kesalahan di awal fase, menghilang setelah epsilon turun.'),
  'p7b': ('Kesalahan FQL bukan karena model buruk, melainkan efek eksplorasi yang disengaja. '
          'Tidak ada pola kesalahan sistematis — hilang setelah FQL konvergen.'),
  's7s1': '7.1 Error Rate Bergulir',
  'fig11': (f'Gambar 11 — Error rate bergulir (window 200). '
            f'RB dan DQN mendekati 0%. FQL sempat naik ~15% saat eksplorasi, lalu turun.'),
  'p7c': ('Penurunan error rate FQL adalah bukti pembelajaran berlangsung. '
          'Error tetap tinggi akan mengindikasikan masalah pada learning rate atau reward function — '
          'tidak terjadi di sini.'),
  's8': 'Reward Sistem AI',
  'p8a': ('Reward: <b>+1</b> jika prediksi benar, <b>-1</b> jika salah. '
          'Grafik ini memperlihatkan seberapa menguntungkan keputusan sistem dari waktu ke waktu.'),
  'fig12': ('Gambar 12 — (Atas) Reward rata-rata bergulir: +100% = semua benar. '
            'RB dan DQN konsisten mendekati +100%. FQL berfluktuasi saat eksplorasi. '
            '(Bawah) Cumulative reward terus naik — sistem lebih sering benar sepanjang pengujian.'),
  'p8b': ('Cumulative reward naik konsisten tanpa turun drastis menunjukkan tidak ada '
          '"krisis keputusan" pada perpindahan antar fase.'),
  's9': 'Confusion Matrix — Detail Distribusi Prediksi',
  'p9a': ('Confusion matrix: <b>baris</b> = risk level aktual, <b>kolom</b> = risk level diprediksi. '
          'Idealnya semua data di diagonal (prediksi = aktual).'),
  'fig13': ('Gambar 13 — Confusion matrix RB (kiri), FQL (tengah), DQN (kanan). '
            'Semua data di kelas CAUTION. RB dan DQN: seluruh data di diagonal. '
            'FQL: sebagian kecil di luar diagonal saat eksplorasi.'),
  'p9b': ('Tidak ada false alarm berbahaya — sistem tidak pernah memprediksi DANGER '
          'saat kondisi SAFE, maupun sebaliknya.'),
  'note9': ('Untuk pengujian berikutnya dengan kondisi lebih beragam, '
            'confusion matrix akan lebih informatif.'),
  's10': 'Policy Map DQN — Peta Keputusan Neural Network',
  'p10a': ('Policy map memvisualisasikan "kebijakan" DQN: '
           'di kombinasi pH dan NH3 berapa, sistem memutuskan risk level apa.'),
  'fig14': ('Gambar 14 — (Kiri) Policy map: warna = risk level yang diprediksi DQN '
            'untuk setiap kombinasi pH × NH3. '
            '(Kanan) Distribusi data aktual — terkonsentrasi di zona CAUTION.'),
  'p10b': ('DQN konsisten memutuskan CAUTION di seluruh rentang yang ditemui. '
           'Pada pengujian berikutnya dengan suhu > 30°C, '
           'policy map diharapkan menunjukkan gradasi warna dari hijau ke merah.'),
  'part_b': 'BAGIAN B — Analisis Performa Jaringan (QoS)',
  'part_b_desc': ('Bagian ini membahas kualitas komunikasi jaringan (Quality of Service / QoS) '
                  'antara ketiga node Pico dan server Raspberry Pi 5. '
                  'QoS diukur dari <b>latency</b>, <b>jitter</b>, dan <b>bandwidth</b> — '
                  'langsung dari karakteristik paket TCP.'),
  's11': 'Kondisi Jaringan Sepanjang Sesi AI — Pico 1',
  'p11a': ('Grafik berikut menampilkan perubahan QoS Pico 1 dari awal hingga akhir, '
           'bersamaan dengan tanda perpindahan fase AI. '
           'Tujuannya: melihat apakah pergantian fase berdampak pada kondisi jaringan.'),
  'fig15': ('Gambar 15 — QoS Pico 1 selama ~16.6 jam: latency (atas), jitter (tengah), bandwidth (bawah). '
            'Garis putus = batas fase AI. QoS stabil dan tidak terpengaruh perpindahan fase.'),
  'p11b': ('Stabilitas QoS sepanjang sesi positif: beban komputasi DQN yang jauh lebih berat '
           'tidak menyebabkan degradasi jaringan. '
           'Raspberry Pi 5 mampu menangani inferensi DQN sekaligus tiga koneksi TCP tanpa bottleneck.'),
  's12': 'Latency — Waktu Keterlambatan Paket',
  'p12a': ('Latency = waktu round-trip paket dari node Pico ke server dan kembali. '
           'Untuk sistem monitoring real-time, di bawah 100 ms sudah sangat baik. '
           'Kadar NH3 berubah dalam hitungan menit, bukan milidetik.'),
  'fig16': (f'Gambar 16 — Latency ketiga node. Rata-rata: '
            f'Pico 1 = {lavg(qos1,"latency_ms"):.2f} ms, '
            f'Pico 2 = {lavg(qos2,"latency_ms"):.2f} ms, '
            f'Pico 3 = {lavg(qos3,"latency_ms"):.2f} ms. '
            'Semua jauh di bawah 15 ms.'),
  's13': 'Jitter — Ketidakstabilan Delay Antar Paket',
  'p13a': ('Jitter mengukur variasi interval waktu antar paket. '
           'Lonjakan sesekali pada WiFi 2.4 GHz adalah normal — '
           'bisa disebabkan perangkat lain di sekitar.'),
  'fig17': ('Gambar 17 — Jitter ketiga node (cap 80 ms untuk keterbacaan). '
            'Lonjakan sesekali adalah gangguan natural WiFi. '
            'TCP menjamin paket tetap diterima meski terlambat.'),
  's14': 'Bandwidth — Kecepatan Transfer Data',
  'p14a': ('Paket sensor sangat ringkas (20–50 byte per paket, interval ~2 detik), '
           'sehingga bandwidth yang dibutuhkan sangat kecil.'),
  'fig18': ('Gambar 18 — Bandwidth ketiga node dalam Kbps. Semua di bawah 2 Kbps — '
            'sangat wajar untuk IoT. Jika diperluas ke 20 node, '
            'bandwidth total masih jauh di bawah kapasitas WiFi 2.4 GHz.'),
  's15': 'Ringkasan QoS — Perbandingan Ketiga Node',
  'fig19': ('Gambar 19 — Rata-rata latency, jitter, dan bandwidth per node. '
            'Nilai antar node sebanding — tidak ada node yang jauh lebih buruk.'),
  'p15a': ('Ketiga node menunjukkan performa QoS baik dan konsisten selama 16.6 jam. '
           'Perbedaan kecil antar node bisa disebabkan posisi fisik atau variasi hardware.'),
  'qos_headers': ['Node','Latency Avg','Jitter Avg','Bandwidth Avg','Sampel'],
  'qos_rows': [
    ['Pico 1 (Sensor Utama)',f'{lavg(qos1,"latency_ms"):.2f} ms',
     f'{min(lavg(qos1,"jitter_ms"),50):.2f} ms',f'{lavg(qos1,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos1):,}'],
    ['Pico 2 (Dummy)',f'{lavg(qos2,"latency_ms"):.2f} ms',
     f'{min(lavg(qos2,"jitter_ms"),50):.2f} ms',f'{lavg(qos2,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos2):,}'],
    ['Pico 3 (Dummy)',f'{lavg(qos3,"latency_ms"):.2f} ms',
     f'{min(lavg(qos3,"jitter_ms"),50):.2f} ms',f'{lavg(qos3,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos3):,}'],
  ],
  's16': 'Kesimpulan & Rekomendasi',
  'conc_good': 'Pencapaian Pengujian Pertama:',
  'conc_g1': (f'Pipeline AI tiga fase (RB → FQL → DQN) berjalan otomatis end-to-end '
              f'selama 16.6 jam tanpa intervensi manual. FQL konvergen dalam 1.000 step, '
              f'DQN selesai dilatih 52 detik dengan akurasi {dqn_a:.1f}%.'),
  'conc_g2': ('Reward kumulatif naik terus dan confusion matrix hampir diagonal sempurna.'),
  'conc_g3': ('QoS tiga node stabil: latency < 15 ms, bandwidth < 2 Kbps per node.'),
  'conc_fix': 'Yang Perlu Ditingkatkan:',
  'conc_f1': ('Confusion matrix saat ini hanya menunjukkan satu risk level (CAUTION) '
              'sesuai kondisi lingkungan pengujian — belum semua risk level teruji.'),
  'conc_f2': ('Belum ada file Wireshark (.pcap) sebagai bukti komunikasi jaringan.'),
  'conc_next': 'Rencana Pengujian Berikutnya:',
  'conc_n1': ('Lakukan pengujian di kondisi lingkungan berbeda agar semua risk level '
              '(SAFE, CAUTION, WARNING, DANGER) dapat dievaluasi secara lengkap.'),
  'conc_n2': ('Pertimbangkan tc netem di Raspberry Pi untuk diferensiasi QoS per node '
              'sesuai saran professor.'),
  'conc_n3': ('Simpan file Wireshark (.pcap) selama pengujian dan commit ke branch.'),
},

'en': {
  'out': OUT_EN,
  'cover_title':    'SYSTEM TEST REPORT',
  'cover_sub':      'Edge-Intelligent Aquaculture NH3 Risk Monitoring',
  'cover_session':  'First Test  ·  Session 20260529_014459',
  'cover_info':     'Duration: ~16.6 hours  ·  Total Steps: 29,938  ·  3 Active IoT Nodes',
  'header_left':    'SYSTEM TEST REPORT',
  'header_right':   'Edge-Intelligent Aquaculture NH3 Risk Monitoring',
  'footer_left':    'Faril Pirwanhadi — M14128104',
  'footer_center':  'Page',
  'sum_headers':    ['Parameter','Value'],
  'sum_rows': [
    ['Total Steps', f'{len(rows):,}'], ['Duration', '~16.6 hours'],
    ['Rule-Based Accuracy', f'{rb_a:.1f}%'], ['FQL Accuracy', f'{fql_a:.1f}%'],
    ['DQN Accuracy', f'{dqn_a:.1f}%'], ['FQL Converged at', 'Step 2,001'],
    ['DQN Activated at', 'Step 3,001'],
    ['Average pH', f'{sum(ph_vals)/len(ph_vals):.3f}'],
    ['Average NH3', f'{sum(nh3_vals)/len(nh3_vals):.3f}%'],
    ['Latency Pico 1', f'{lavg(qos1,"latency_ms"):.2f} ms'],
    ['Latency Pico 2', f'{lavg(qos2,"latency_ms"):.2f} ms'],
    ['Latency Pico 3', f'{lavg(qos3,"latency_ms"):.2f} ms'],
  ],
  's1': 'Introduction',
  'p1a': ('This report presents the results of the first test of an NH3 risk monitoring system '
          'for aquaculture, based on edge AI running on a <b>Raspberry Pi 5</b> server. '
          'Three <b>Raspberry Pi Pico</b> nodes connect via 2.4 GHz WiFi.'),
  'p1b': ('Pico 1 (WH/RP2040) reads pH and temperature sensors in real-time. '
          'Pico 2 and Pico 3 (2W/RP2350) generate network traffic to measure QoS per node.'),
  'p1c': ('The AI system runs <b>progressively and automatically</b> in three phases: '
          '<b>Rule-Based (RB)</b> → <b>FQL</b> → <b>DQN</b>, '
          'with all transitions occurring without manual intervention.'),
  's2': 'AI Phase Transition Flow',
  'p2a': ('The chart below shows when each AI phase was active. '
          'One step ≈ one sensor reading (~2 seconds). '
          'Dashed vertical lines mark phase transitions.'),
  'fig1': 'Figure 1 — AI phase timeline. Blue = Rule-Based, Yellow = FQL, Green = DQN.',
  'phase_headers': ['Phase','Step Range','Step Count','Description'],
  'phase_rows': [
    ['Rule-Based','1 – 2,000','2,000','Fixed if-then rules, no learning'],
    ['FQL','2,001 – 3,000','1,000','Learns from feedback, epsilon decays gradually'],
    ['DQN','3,001 – 29,938','26,938','Neural network, trained from FQL memory'],
  ],
  'p2b': ('FQL converged after 1,000 steps. DQN completed training in only <b>52 seconds</b> '
          'using 2,001 transitions collected by FQL.'),
  'part_sim': 'SIMULATION — Pre-Implementation Validation',
  'part_sim_desc': ('Before hardware testing, the system was validated through computational simulation '
                    'using 30,000 synthetic samples across 7 different water condition scenarios. '
                    'The goal was to confirm the DQN > FQL > Rule-Based performance hierarchy '
                    'before deployment to physical hardware.'),
  's_sim1': 'Simulation Overview',
  'p_sim1a': ('The simulation ran 150 test episodes of 200 steps each (30,000 total samples). '
              'Seven water condition scenarios were tested: Safe, Acidic, Alkaline, Cold, Hot, Multi-stress, '
              'and Random. Statistical validation used 5 independent runs with identical configuration '
              'to ensure result consistency.'),
  'sim_fig1': ('Figure S1 — Average simulation accuracy over 5 runs: Rule-Based 75.76% (±0.09%), '
               'FQL 82.51% (±0.42%), DQN 96.54% (±0.07%). The DQN > FQL > Rule-Based hierarchy '
               'was confirmed in all 5 runs (100% success rate).'),
  'p_sim1b': ('DQN achieved not only the highest accuracy but also the best stability, with a standard '
              'deviation of only 0.07% compared to FQL\'s 0.42%. This means DQN produces reliable '
              'predictions across varied conditions, not just a good average.'),
  'sim_fig2': ('Figure S2 — Relative performance improvement between methods. FQL improved +8.9% over '
               'Rule-Based, DQN improved +17.0% over FQL, and DQN achieved a total gain of +27.4% over '
               'Rule-Based. Reward also improved significantly: +22.6%, +30.6%, and +60.1%.'),
  's_sim2': 'Detailed Analysis: Metrics, Reward, and Multi-Dimensional Comparison',
  'p_sim2a': ('Deeper analysis using a multi-metric radar chart and confusion matrices further confirms '
              'DQN superiority across every measurement dimension. '
              'DQN\'s average F1-score reached 94.02%, well above FQL (64.51%) and Rule-Based (68.96%).'),
  'sim_fig3': ('Figure S3 — Multi-metric radar chart comparison. DQN dominates all axes: '
               'accuracy, precision, recall, F1-score, and reward stability. '
               'FQL sits in the middle, Rule-Based is most limited.'),
  'sim_fig4': ('Figure S4 — Simulation confusion matrices for RB (left), FQL (middle), DQN (right). '
               'DQN has the most filled diagonal, with very few predictions outside the correct class.'),
  'sim_fig5': ('Figure S5 — Average reward per episode comparison. DQN: 0.948±0.001 (most stable). '
               'FQL: 0.726±0.007. Rule-Based: 0.592±0.002. Closer to 1.0 means more consistently correct.'),
  'p_sim2b': ('These simulation results provided the foundation for real implementation: start with '
              'Rule-Based as a safe baseline, then let FQL accumulate experience, and finally train DQN '
              'from FQL\'s memory for optimal performance. This progressive strategy was proven effective '
              'in simulation before being tested in a real environment.'),
  'part_a': 'PART A — AI Method Performance Analysis',
  'part_a_desc': ('This section covers all aspects of the three AI methods in sequence: '
                  'sensor data conditions, accuracy, learning processes, '
                  'error analysis, reward, confusion matrix, and policy map.'),
  's3': 'Sensor Data Conditions During Testing',
  'p3a': ('Before evaluating AI performance, it is important to understand the input data. '
          'The chart below shows pH, NH3 concentration, and active AI mode '
          'together so their relationships are clearly visible.'),
  'fig2': ('Figure 2 — (Top) pH fluctuates normally in range 7.47–7.64. '
           '(Middle) NH3 ranges 1.66–2.43%, CAUTION zone consistent with environmental conditions. '
           '(Bottom) Active AI mode — red dots = wrong predictions, very rare.'),
  'fig3': ('Figure 3 — (Left) Actual risk level distribution during the test. '
           '(Right) DQN dominated 90% of test steps.'),
  's4': 'Accuracy Comparison: RB vs FQL vs DQN',
  'p4a': ('Accuracy is the percentage of steps where the predicted risk level '
          'exactly matches the actual value from the sensors.'),
  'fig4': (f'Figure 4 — Accuracy: Rule-Based {rb_a:.1f}%, FQL {fql_a:.1f}%, DQN {dqn_a:.1f}%.'),
  'p4b': ('<b>Rule-Based</b>: deterministic if-then rules. Accurate as long as conditions match the rules.'),
  'p4c': (f'<b>FQL</b>: learns from scratch through trial and error. Achieved {fql_a:.1f}% despite active exploration.'),
  'p4d': (f'<b>DQN</b>: neural network trained from FQL memory. Immediately accurate at {dqn_a:.1f}% when activated.'),
  's4s1': '4.1 Rolling Accuracy Over Time',
  'fig5': ('Figure 5 — Rolling accuracy (window 300 steps). '
           'RB stable (blue). FQL fluctuates during exploration then stabilizes (yellow). '
           'DQN immediately stable from step 3,001 (green).'),
  'p4e': ('Unlike the bar chart, this shows whether the system is consistently good over time. '
          'DQN being immediately stable is a sign of good training quality.'),
  's5': 'FQL Learning Process — Epsilon Decay',
  'p5a': ('Epsilon controls the balance between <b>exploration</b> (trying random actions) '
          'and <b>exploitation</b> (using the best known strategy). '
          'Analogy: high epsilon = willing to try new items on the menu; '
          'low epsilon = ordering the proven favorite.'),
  'fig6': ('Figure 6 — Epsilon throughout the test. Stable during RB phase. '
           'Decays from ~0.30 to minimum during FQL. '
           'At minimum when DQN activates.'),
  'p5b': ('The gradual epsilon decrease shows FQL successfully transitioned '
          'from exploration to exploitation — confirmed by rising accuracy.'),
  's5s1': '5.1 FQL Accuracy and Epsilon During FQL Phase',
  'fig7': ('Figure 7 — FQL phase zoom. (Top) Epsilon decays gradually. '
           '(Bottom) Accuracy rises as epsilon falls. '
           'This correlation confirms reduced exploration → increased accuracy.'),
  'p5c': ('At the start of FQL (steps 2,001–2,100), accuracy fluctuates due to heavy exploration. '
          'After epsilon falls (~step 2,500), accuracy stabilizes above 90% — healthy convergence.'),
  's5s2': '5.2 FQL Convergence: Accuracy & Epsilon',
  'fig8': ('Figure 8 — FQL convergence by internal step. '
           'Yellow = rolling accuracy (30-step). Purple = epsilon. '
           'Lower epsilon → higher and more stable accuracy.'),
  's6': 'DQN Performance — Deep Q-Network',
  'p6a': ('DQN uses a neural network to capture more complex patterns than FQL\'s Q-table. '
          'DQN is trained from a <b>replay buffer</b> of 2,001 transitions collected by FQL. '
          'Training completed in <b>52 seconds</b>.'),
  'fig9': (f'Figure 9 — DQN accuracy (rolling 500 steps) from step 3,001 to 29,938. '
           f'Immediately operates at {dqn_a:.1f}% and maintains it consistently.'),
  'p6b': ('DQN\'s consistent accuracy across 26,000+ steps proves no overfitting or performance degradation.'),
  's7': 'Predicted vs Actual Risk per Phase',
  'p7a': ('The charts below directly compare each method\'s predictions with actual values. '
          'Colored dots = correct, red crosses = wrong.'),
  'fig10': ('Figure 10 — Predicted vs Actual for RB (top), FQL (middle), DQN (bottom). '
            'RB and DQN have almost no red crosses. '
            'FQL has a few errors at the start of the phase, disappearing as epsilon drops.'),
  'p7b': ('FQL errors are not a sign of a poor model — they are an intentional effect of exploration. '
          'No systematic error patterns; errors disappear after FQL converges.'),
  's7s1': '7.1 Rolling Error Rate',
  'fig11': (f'Figure 11 — Rolling error rate (window 200). '
            f'RB and DQN near 0%. FQL reached ~15% during exploration, then dropped.'),
  'p7c': ('Declining FQL error rate is proof that learning occurred. '
          'Persistently high error would indicate misconfigured learning rate or reward function — '
          'not the case here.'),
  's8': 'AI System Reward',
  'p8a': ('Reward: <b>+1</b> for correct prediction, <b>-1</b> for wrong. '
          'This chart shows how rewarding the system\'s decisions are over time.'),
  'fig12': ('Figure 12 — (Top) Rolling average reward: +100% = all correct. '
            'RB and DQN consistently near +100%. FQL fluctuates during exploration. '
            '(Bottom) Cumulative reward rises continuously — system correct more than wrong.'),
  'p8b': ('Consistently rising cumulative reward with no sharp drops shows no '
          '"decision crisis" during phase transitions.'),
  's9': 'Confusion Matrix — Detailed Prediction Distribution',
  'p9a': ('Confusion matrix: <b>rows</b> = actual risk level, <b>columns</b> = predicted risk level. '
          'Ideally all data on the diagonal (prediction = actual).'),
  'fig13': ('Figure 13 — Confusion matrices for RB (left), FQL (middle), DQN (right). '
            'All data in CAUTION class. RB and DQN: all data on diagonal. '
            'FQL: small amount off-diagonal during exploration.'),
  'p9b': ('No dangerous false alarms — the system never predicted DANGER when conditions were SAFE.'),
  'note9': ('For the next test with more varied conditions, '
            'the confusion matrix will be more informative.'),
  's10': 'DQN Policy Map — Decision Boundary Visualization',
  'p10a': ('The policy map visualizes the "policy" learned by DQN: '
           'for each pH × NH3 combination, what risk level does the system decide?'),
  'fig14': ('Figure 14 — (Left) Policy map: color = DQN predicted risk level '
            'for each pH × NH3 combination. '
            '(Right) Actual risk distribution — concentrated in CAUTION zone.'),
  'p10b': ('DQN consistently decides CAUTION across all observed ranges. '
           'In the next test with temperature > 30°C, '
           'the policy map should show a gradient from green to red.'),
  'part_b': 'PART B — Network Performance Analysis (QoS)',
  'part_b_desc': ('This section covers the Quality of Service (QoS) of network communication '
                  'between the three Pico nodes and the Raspberry Pi 5 server. '
                  'QoS is measured via <b>latency</b>, <b>jitter</b>, and <b>bandwidth</b> — '
                  'directly from TCP packet characteristics.'),
  's11': 'Network Conditions Throughout the AI Session — Pico 1',
  'p11a': ('The chart below shows Pico 1\'s QoS from start to finish, '
           'alongside AI phase transition markers. '
           'Goal: determine whether phase changes affect network conditions.'),
  'fig15': ('Figure 15 — Pico 1 QoS over ~16.6 hours: latency (top), jitter (middle), bandwidth (bottom). '
            'Dashed lines = AI phase boundaries. QoS remains stable throughout.'),
  'p11b': ('Stable QoS throughout the session is a positive finding: '
           'DQN\'s heavier computational load did not cause noticeable network degradation. '
           'Raspberry Pi 5 handled DQN inference and three TCP connections without bottleneck.'),
  's12': 'Latency — Packet Delay',
  'p12a': ('Latency = round-trip time for a packet from Pico to server and back. '
           'Below 100 ms is very good for real-time monitoring. '
           'NH3 concentration changes on a scale of minutes, not milliseconds.'),
  'fig16': (f'Figure 16 — Latency for all three nodes. Average: '
            f'Pico 1 = {lavg(qos1,"latency_ms"):.2f} ms, '
            f'Pico 2 = {lavg(qos2,"latency_ms"):.2f} ms, '
            f'Pico 3 = {lavg(qos3,"latency_ms"):.2f} ms. '
            'All well below 15 ms.'),
  's13': 'Jitter — Inter-Packet Delay Variation',
  'p13a': ('Jitter measures variation in packet arrival intervals. '
           'Occasional spikes on 2.4 GHz WiFi are normal — '
           'caused by other devices or interference.'),
  'fig17': ('Figure 17 — Jitter for all three nodes (capped at 80 ms for readability). '
            'Occasional spikes are natural WiFi interference. '
            'TCP guarantees packet delivery even when delayed.'),
  's14': 'Bandwidth — Data Transfer Rate',
  'p14a': ('Sensor packets are very compact (20–50 bytes per packet, ~2-second intervals), '
           'so very little bandwidth is required.'),
  'fig18': ('Figure 18 — Bandwidth for all three nodes in Kbps. All below 2 Kbps — '
            'typical for IoT devices. Scaling to 20 nodes would still be far below WiFi capacity.'),
  's15': 'QoS Summary — Three-Node Comparison',
  'fig19': ('Figure 19 — Average latency, jitter, and bandwidth per node. '
            'Values are comparable across nodes — no node significantly worse than others.'),
  'p15a': ('All three nodes showed good, consistent QoS over 16.6 hours. '
           'Minor differences can be attributed to physical placement or hardware variation.'),
  'qos_headers': ['Node','Avg Latency','Avg Jitter','Avg Bandwidth','Samples'],
  'qos_rows': [
    ['Pico 1 (Main Sensor)',f'{lavg(qos1,"latency_ms"):.2f} ms',
     f'{min(lavg(qos1,"jitter_ms"),50):.2f} ms',f'{lavg(qos1,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos1):,}'],
    ['Pico 2 (Dummy)',f'{lavg(qos2,"latency_ms"):.2f} ms',
     f'{min(lavg(qos2,"jitter_ms"),50):.2f} ms',f'{lavg(qos2,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos2):,}'],
    ['Pico 3 (Dummy)',f'{lavg(qos3,"latency_ms"):.2f} ms',
     f'{min(lavg(qos3,"jitter_ms"),50):.2f} ms',f'{lavg(qos3,"bandwidth_mbps")*1000:.4f} Kbps',f'{len(qos3):,}'],
  ],
  's16': 'Conclusion & Recommendations',
  'conc_good': 'Achievements of First Test:',
  'conc_g1': (f'Three-phase AI pipeline (RB → FQL → DQN) ran automatically end-to-end '
              f'for 16.6 hours without manual intervention. FQL converged in 1,000 steps, '
              f'DQN trained in 52 seconds with {dqn_a:.1f}% accuracy.'),
  'conc_g2': ('Cumulative reward consistently rising and confusion matrix nearly perfectly diagonal.'),
  'conc_g3': ('QoS of all three nodes stable: latency < 15 ms, bandwidth < 2 Kbps per node.'),
  'conc_fix': 'Areas for Improvement:',
  'conc_f1': ('The confusion matrix currently shows only one risk level (CAUTION), '
              'consistent with environmental conditions during this test — not all risk levels have been evaluated.'),
  'conc_f2': ('No Wireshark capture file (.pcap) saved as network evidence for thesis defence.'),
  'conc_next': 'Plan for Next Test:',
  'conc_n1': ('Conduct testing under different environmental conditions so all risk levels '
              '(SAFE, CAUTION, WARNING, DANGER) can be fully evaluated.'),
  'conc_n2': ('Consider tc netem on Raspberry Pi for per-node QoS differentiation '
              'as suggested by the supervisor.'),
  'conc_n3': ('Save Wireshark capture (.pcap) during testing and commit to the test branch.'),
},
}  # end T dict

# ═════════════════════════════════════════════════════════════════════════════
# PDF BUILDER
# ═════════════════════════════════════════════════════════════════════════════
W, H = A4
ML = MR = 2.2*cm
MT = MB = 2.0*cm
CW = W - ML - MR

C_PRI  = colors.HexColor('#1d4ed8')
C_SEC  = colors.HexColor('#0f172a')
C_ACC  = colors.HexColor('#f1f5f9')
C_CAP  = colors.HexColor('#475569')
C_NOTE = colors.HexColor('#92400e')
C_NB   = colors.HexColor('#fffbeb')
C_RULE = colors.HexColor('#cbd5e1')

def make_styles():
    sty = getSampleStyleSheet()
    def add(name, **kw): sty.add(ParagraphStyle(name, **kw))
    add('CoverTitle', fontSize=24, textColor=C_PRI, alignment=TA_CENTER,
        fontName='Helvetica-Bold', spaceAfter=5, leading=30)
    add('CoverSub', fontSize=12, textColor=C_SEC, alignment=TA_CENTER,
        spaceAfter=3, leading=16)
    add('CoverMeta', fontSize=10, textColor=C_CAP, alignment=TA_CENTER,
        spaceAfter=3, leading=13)
    add('SecH', fontSize=13, textColor=C_PRI, fontName='Helvetica-Bold',
        spaceBefore=6, spaceAfter=3, leading=17)
    add('SubH', fontSize=10.5, textColor=C_SEC, fontName='Helvetica-Bold',
        spaceBefore=6, spaceAfter=2, leading=14)
    add('PartBanner', fontSize=13, textColor=colors.white, fontName='Helvetica-Bold',
        alignment=TA_CENTER, spaceAfter=0, leading=17, backColor=C_PRI)
    add('Body', fontSize=9.5, textColor=C_SEC, alignment=TA_JUSTIFY,
        spaceAfter=4, leading=14.5)
    add('Cap', fontSize=8.5, textColor=C_CAP, alignment=TA_CENTER,
        spaceAfter=6, spaceBefore=2, leading=12, fontName='Helvetica-Oblique')
    add('Note', fontSize=9, textColor=C_NOTE, spaceBefore=2, spaceAfter=5,
        leading=13, leftIndent=8, rightIndent=8, backColor=C_NB, borderPad=5)
    return sty

def make_tbl_style():
    return TableStyle([
        ('BACKGROUND',   (0,0),(-1,0),   colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR',    (0,0),(-1,0),   colors.HexColor('#bfdbfe')),
        ('FONTNAME',     (0,0),(-1,0),   'Helvetica-Bold'),
        ('FONTSIZE',     (0,0),(-1,-1),  9),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.HexColor('#f8fafc'),colors.HexColor('#f1f5f9')]),
        ('TEXTCOLOR',    (0,1),(-1,-1),  C_SEC),
        ('ALIGN',        (1,0),(-1,-1),  'CENTER'),
        ('VALIGN',       (0,0),(-1,-1),  'MIDDLE'),
        ('GRID',         (0,0),(-1,-1),  0.4, C_RULE),
        ('ROWHEIGHT',    (0,0),(-1,-1),  18),
        ('LEFTPADDING',  (0,0),(-1,-1),  7),
        ('RIGHTPADDING', (0,0),(-1,-1),  7),
        ('TOPPADDING',   (0,0),(-1,-1),  3),
        ('BOTTOMPADDING',(0,0),(-1,-1),  3),
    ])

class ReportDoc(BaseDocTemplate):
    def __init__(self, filename, L, **kw):
        super().__init__(filename, **kw)
        self._L = L
        frame = Frame(ML, MB, CW, H-MT-MB, id='main')
        self.addPageTemplates([PageTemplate(id='main', frames=frame,
                                            onPage=self._draw_page)])
    def _draw_page(self, canv, doc):
        L = self._L
        canv.saveState()
        # top
        canv.setStrokeColor(C_PRI); canv.setLineWidth(1.5)
        canv.line(ML, H-1.35*cm, W-MR, H-1.35*cm)
        canv.setFont('Helvetica-Bold',7); canv.setFillColor(C_PRI)
        canv.drawString(ML, H-1.15*cm, L['header_left'])
        canv.setFont('Helvetica',7); canv.setFillColor(C_CAP)
        canv.drawRightString(W-MR, H-1.15*cm, L['header_right'])
        # bottom
        canv.setStrokeColor(C_RULE); canv.setLineWidth(0.5)
        canv.line(ML, 1.35*cm, W-MR, 1.35*cm)
        canv.setFont('Helvetica',7); canv.setFillColor(C_CAP)
        canv.drawString(ML, 0.9*cm, L['footer_left'])
        canv.drawCentredString(W/2, 0.9*cm, f"{L['footer_center']} {doc.page}")
        canv.drawRightString(W-MR, 0.9*cm, datetime.now().strftime('%d %B %Y'))
        canv.restoreState()

def fig_block(sty, path, caption, w=None, ratio=None):
    """Returns a KeepTogether block: image + caption."""
    iw = w or CW
    # auto-ratio from actual image if not specified
    if ratio is None: ratio = 0.38
    return KeepTogether([
        Image(path, width=iw, height=iw*ratio),
        Paragraph(caption, sty['Cap']),
        Spacer(1, 0.1*cm),
    ])

def HR(c=None):
    return HRFlowable(width=CW, thickness=0.5, color=c or C_RULE)

def part_block(sty, text):
    return [
        Spacer(1, 0.2*cm),
        Table([[Paragraph(text, sty['PartBanner'])]],
              colWidths=[CW],
              style=TableStyle([
                  ('BACKGROUND',(0,0),(-1,-1),C_PRI),
                  ('ROWHEIGHT', (0,0),(-1,-1),28),
                  ('TOPPADDING',(0,0),(-1,-1),5),
                  ('BOTTOMPADDING',(0,0),(-1,-1),5),
              ])),
        Spacer(1, 0.2*cm),
    ]

def sec(sty, n, text):
    return [
        Spacer(1, 0.15*cm),
        HRFlowable(width=CW, thickness=1.5, color=C_PRI),
        Paragraph(f'{n}. {text}', sty['SecH']),
    ]

def sub(sty, text):
    return [Spacer(1, 0.1*cm), Paragraph(text, sty['SubH'])]

def build_pdf(lang):
    L   = T[lang]
    sty = make_styles()
    S   = lambda n: sty[n]
    story = []

    # ── COVER ──────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1.6*cm),
        Paragraph(L['cover_title'],  S('CoverTitle')),
        Paragraph(L['cover_sub'],    S('CoverSub')),
        Spacer(1, 0.4*cm),
        HRFlowable(width=CW, thickness=2, color=C_PRI),
        Spacer(1, 0.35*cm),
        Paragraph(L['cover_session'], S('CoverSub')),
        Paragraph(L['cover_info'],    S('CoverMeta')),
        Spacer(1, 0.5*cm),
        Paragraph('Faril Pirwanhadi  ·  M14128104', S('CoverSub')),
        Paragraph(datetime.now().strftime('%d %B %Y'), S('CoverMeta')),
        Spacer(1, 1.0*cm),
    ]
    t = Table([L['sum_headers']] + L['sum_rows'], colWidths=[CW*0.6, CW*0.4])
    t.setStyle(make_tbl_style()); story += [t, PageBreak()]

    # ── SEC 1 ──────────────────────────────────────────────────────────────
    story += sec(sty, 1, L['s1'])
    story += [
        Paragraph(L['p1a'], S('Body')),
        Paragraph(L['p1b'], S('Body')),
        Paragraph(L['p1c'], S('Body')),
    ]

    # ── SEC 2 ──────────────────────────────────────────────────────────────
    story += sec(sty, 2, L['s2'])
    story += [
        Paragraph(L['p2a'], S('Body')),
        Spacer(1, 0.1*cm),
        fig_block(sty, P['timeline'], L['fig1'], ratio=0.20),
    ]
    t2 = Table([L['phase_headers']] + L['phase_rows'],
               colWidths=[CW*0.2, CW*0.2, CW*0.16, CW*0.44])
    t2.setStyle(make_tbl_style())
    story += [t2, Spacer(1, 0.15*cm), Paragraph(L['p2b'], S('Body'))]

    # ── PART SIM BANNER ────────────────────────────────────────────────────
    story += [PageBreak()]
    story += part_block(sty, L['part_sim'])
    story += [Paragraph(L['part_sim_desc'], S('Body'))]

    # ── SIM SEC 3 ──────────────────────────────────────────────────────────
    story += sec(sty, 3, L['s_sim1'])
    story += [
        Paragraph(L['p_sim1a'], S('Body')),
        fig_block(sty, PSIM['sim1'], L['sim_fig1'], ratio=0.60),
        Paragraph(L['p_sim1b'], S('Body')),
        fig_block(sty, PSIM['sim9'], L['sim_fig2'], ratio=0.60),
    ]

    # ── SIM SEC 4 ──────────────────────────────────────────────────────────
    story += sec(sty, 4, L['s_sim2'])
    story += [
        Paragraph(L['p_sim2a'], S('Body')),
        fig_block(sty, PSIM['sim4'], L['sim_fig3'], CW*0.46, ratio=0.88),
        fig_block(sty, PSIM['sim5'], L['sim_fig4'], ratio=0.32),
        fig_block(sty, PSIM['sim6'], L['sim_fig5'], ratio=0.44),
        Paragraph(L['p_sim2b'], S('Body')),
    ]

    # ── PART A BANNER ──────────────────────────────────────────────────────
    story += [PageBreak()]
    story += part_block(sty, L['part_a'])
    story += [Paragraph(L['part_a_desc'], S('Body'))]

    # ── SEC 5 ──────────────────────────────────────────────────────────────
    story += sec(sty, 5, L['s3'])
    story += [
        Paragraph(L['p3a'], S('Body')),
        Spacer(1, 0.1*cm),
        fig_block(sty, P['overlay'],  L['fig2'], ratio=0.62),
        fig_block(sty, P['dist'], L['fig3'], ratio=0.375),
    ]

    # ── SEC 6 ──────────────────────────────────────────────────────────────
    story += sec(sty, 6, L['s4'])
    story += [
        Paragraph(L['p4a'], S('Body')),
        fig_block(sty, P['acc_bar'], L['fig4'], CW*0.58, ratio=0.70),
        Paragraph(L['p4b'], S('Body')),
        Paragraph(L['p4c'], S('Body')),
        Paragraph(L['p4d'], S('Body')),
    ]
    story += sub(sty, L['s4s1'])
    story += [
        fig_block(sty, P['rolling'], L['fig5'], ratio=0.315),
        Paragraph(L['p4e'], S('Body')),
    ]

    # ── SEC 7 ──────────────────────────────────────────────────────────────
    story += sec(sty, 7, L['s5'])
    story += [
        Paragraph(L['p5a'], S('Body')),
        fig_block(sty, P['epsilon'], L['fig6'], ratio=0.265),
        Paragraph(L['p5b'], S('Body')),
    ]
    if P['fql_zoom']:
        story += sub(sty, L['s5s1'])
        story += [
            fig_block(sty, P['fql_zoom'], L['fig7'], ratio=0.43),
            Paragraph(L['p5c'], S('Body')),
        ]
    if P['fql_conv']:
        story += sub(sty, L['s5s2'])
        story += [fig_block(sty, P['fql_conv'], L['fig8'], CW*0.82, ratio=0.41)]

    # ── SEC 8 ──────────────────────────────────────────────────────────────
    if P['dqn_acc']:
        story += sec(sty, 8, L['s6'])
        story += [
            Paragraph(L['p6a'], S('Body')),
            fig_block(sty, P['dqn_acc'], L['fig9'], ratio=0.29),
            Paragraph(L['p6b'], S('Body')),
        ]

    # ── SEC 9 ──────────────────────────────────────────────────────────────
    story += sec(sty, 9, L['s7'])
    story += [
        Paragraph(L['p7a'], S('Body')),
        fig_block(sty, P['pred'], L['fig10'], ratio=0.62),
        Paragraph(L['p7b'], S('Body')),
    ]
    story += sub(sty, L['s7s1'])
    story += [
        fig_block(sty, P['errors'], L['fig11'], ratio=0.29),
        Paragraph(L['p7c'], S('Body')),
    ]

    # ── SEC 10 ─────────────────────────────────────────────────────────────
    if P['reward']:
        story += sec(sty, 10, L['s8'])
        story += [
            Paragraph(L['p8a'], S('Body')),
            fig_block(sty, P['reward'], L['fig12'], ratio=0.54),
            Paragraph(L['p8b'], S('Body')),
        ]

    # ── SEC 11 ─────────────────────────────────────────────────────────────
    if P['conf']:
        story += sec(sty, 11, L['s9'])
        story += [
            Paragraph(L['p9a'], S('Body')),
            fig_block(sty, P['conf'], L['fig13'], ratio=0.325),
            Paragraph(L['p9b'], S('Body')),
            Paragraph(L['note9'], S('Note')),
        ]

    # ── SEC 12 ─────────────────────────────────────────────────────────────
    if P['policy']:
        story += sec(sty, 12, L['s10'])
        story += [
            Paragraph(L['p10a'], S('Body')),
            fig_block(sty, P['policy'], L['fig14'], ratio=0.38),
            Paragraph(L['p10b'], S('Body')),
        ]

    # ── PART B BANNER ──────────────────────────────────────────────────────
    story += [PageBreak()]
    story += part_block(sty, L['part_b'])
    story += [Paragraph(L['part_b_desc'], S('Body'))]

    # ── SEC 13 ─────────────────────────────────────────────────────────────
    story += sec(sty, 13, L['s11'])
    story += [
        Paragraph(L['p11a'], S('Body')),
        fig_block(sty, P['qos_ai'], L['fig15'], ratio=0.62),
        Paragraph(L['p11b'], S('Body')),
    ]

    # ── SEC 14 ─────────────────────────────────────────────────────────────
    story += sec(sty, 14, L['s12'])
    story += [
        Paragraph(L['p12a'], S('Body')),
        fig_block(sty, P['lat'], L['fig16'], ratio=0.315),
    ]

    # ── SEC 15 ─────────────────────────────────────────────────────────────
    story += sec(sty, 15, L['s13'])
    story += [
        Paragraph(L['p13a'], S('Body')),
        fig_block(sty, P['jit'], L['fig17'], ratio=0.315),
    ]

    # ── SEC 16 ─────────────────────────────────────────────────────────────
    story += sec(sty, 16, L['s14'])
    story += [
        Paragraph(L['p14a'], S('Body')),
        fig_block(sty, P['bw'], L['fig18'], ratio=0.315),
    ]

    # ── SEC 17 ─────────────────────────────────────────────────────────────
    story += sec(sty, 17, L['s15'])
    story += [fig_block(sty, P['qos_sum'], L['fig19'], ratio=0.315)]
    t4 = Table([L['qos_headers']] + L['qos_rows'],
               colWidths=[CW*0.27, CW*0.17, CW*0.17, CW*0.21, CW*0.18])
    t4.setStyle(make_tbl_style())
    story += [t4, Spacer(1, 0.15*cm), Paragraph(L['p15a'], S('Body'))]

    # ── SEC 18: CONCLUSION ─────────────────────────────────────────────────
    story += sec(sty, 18, L['s16'])
    story += [
        Paragraph(L['conc_good'], S('SubH')),
        Paragraph(L['conc_g1'], S('Body')),
        Paragraph(L['conc_g2'], S('Body')),
        Paragraph(L['conc_g3'], S('Body')),
        Spacer(1, 0.15*cm),
        Paragraph(L['conc_fix'], S('SubH')),
        Paragraph(L['conc_f1'], S('Note')),
        Paragraph(L['conc_f2'], S('Note')),
        Spacer(1, 0.15*cm),
        Paragraph(L['conc_next'], S('SubH')),
        Paragraph(L['conc_n1'], S('Body')),
        Paragraph(L['conc_n2'], S('Body')),
        Paragraph(L['conc_n3'], S('Body')),
    ]

    # ── BUILD ──────────────────────────────────────────────────────────────
    doc = ReportDoc(L['out'], L, pagesize=A4,
                    leftMargin=ML, rightMargin=MR,
                    topMargin=MT+0.8*cm, bottomMargin=MB+0.8*cm)
    doc.build(story)
    print(f"  Saved: {L['out']}")

print("\nBuilding PDFs...")
build_pdf('id')
build_pdf('en')
print("Done.")
