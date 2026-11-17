"""Official Microsoft GriTS content metric, alongside strict financial facts."""
import numpy as np
from vendor.grits import grits_con
from table_structure import normalize

def matrix(grids):
 rows=[row for grid in grids for row in grid['cells']]
 width=max((len(row) for row in rows),default=0)
 return np.array([[normalize(x) for x in row]+['']*(width-len(row)) for row in rows],dtype=object).reshape((len(rows),width))

def content_score(reference,predicted):
 a,b=matrix(reference),matrix(predicted)
 f,p,r,bound=grits_con(a,b)
 return dict(f1=float(f),precision=float(p),recall=float(r),upper_bound=float(bound),metric='GriTS_Con',
             note='Official content similarity; partial text credit and blank cells can hide consequential financial errors. Pair with strict associated facts.')
