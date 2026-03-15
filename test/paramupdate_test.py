from swat_toolkit.io.parameters import SWATParam
import pandas as pd


param = r'D:\RSWAT\swatParam.txt'
swat_param = SWATParam(param)

print(swat_param.group_param_by_ext({
    'CN2': -5,
    'SOL_BD': 0.1
}))

print(swat_param.get(['CN2', 'SOL_BD', 'SOL_K']))