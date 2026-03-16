from swat_toolkit.io.writers import HRUWriter
from swat_toolkit.io.parameters import SWATParam
from swat_toolkit.core.txinout import TxInOut
from swat_toolkit.run.run import SWATRun


scenarios = ['history', 'ssp245','ssp340', 'ssp585']


txinout = TxInOut(fr'D:\Project\2025_DEGRESS\SWAT\ba_CungSon\Scenarios\{scenarios[0]}\TxtInOut')

txinout.get_output_file('.rch')
param = SWATParam(r"D:\RSWAT\swatParam.txt")

swat_exe = SWATRun(r"D:\RSWAT\_SWAT_RUN\Rev_695_64rel.exe")

parametter = {
    "CN2"       : (-0.249, 'relative'),
    "ALPHA_BF"  : (0.506, 'replace'),
    "GW_DELAY"  : (436.905, 'replace'),
    "GWQMN"     : (3744.065, 'replace'),
    "RCHRG_DP"  : (0.462, 'relative'),
    "GW_REVAP"  : (1.989, 'relative'),
    "LAT_TTIME" : (134.069, 'relative'),
    "OV_N"      : (0.091, 'relative'),
    "ESCO"      : (0.366, 'relative'),
    "SLSUBBSN"  : (0.107, 'relative'),
    "HRU_SLP"   : (0.203, 'relative'),
    "SOL_AWC"   : (0.32, 'relative'),
    "SOL_K"     : (0.243, 'relative'),
    "SOL_BD"    : (0.138, 'relative'),
    "CH_N2"     : (0.072, 'relative'),
    "CH_K2"     : (407.968, 'relative'),
    "ALPHA_BNK" : (0.112, 'relative'),
    "SURLAG"    : (9.645, 'relative'),
    "EPCO"      : (0.677, 'relative')
}

grouped = param.get_param_by_name(parametter)

values  = {k: v[0] for k, v in parametter.items()}
methods = {k: v[1] for k, v in parametter.items()}

grouped = param.get_param_by_name(values)
print(grouped)
for scenario in scenarios:
    txinout_scenarios = TxInOut(
        fr'D:\Project\2025_DEGRESS\SWAT\ba_CungSon\Scenarios\{scenario}\TxtInOut'
    )

    for ext, ext_params in grouped.items():
        for fpath in txinout.get_all_hru_files(ext):
            writer = HRUWriter(str(fpath))

            for param_name, param_obj in ext_params.items():  # ← .items()
                print(param_name, param_obj)
                par = param.get(param_name)
                value = values.get(param_name)
                method = methods.get(param_name, 'replace')
                writer._update(par, value, ext=ext, method=method)

            writer.save()

    swat_exe.run(txinout_scenarios.directory)

    print(f"✅ Done: {scenario}")
