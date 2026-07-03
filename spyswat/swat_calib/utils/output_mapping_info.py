from typing import List, Dict, Tuple, Optional
from abc import ABC, abstractmethod

from spyswat.logger import Logger

logger = Logger.get_logger(__name__)




# BASE ABSTRACT CLASS: SWATColumnMapping
class SWATColumnMapping(ABC):

    _MAPPING = None

    @classmethod
    @abstractmethod
    def get_mapping(cls) -> Dict:
        pass

    @classmethod
    def get_colspec(cls, key: str) -> Tuple[int, int]:
        if key not in cls._MAPPING:
            raise KeyError(f"Key '{key}' doesn't exist.")
        return cls._MAPPING[key]["colspec"]

    @classmethod
    def get_muti_colspecs(cls, columns: List) -> List[Tuple[int, int]]:
        return [cls.get_colspec(col) for col in columns]

    @classmethod
    def get_all_colspecs(cls) -> List[Tuple[int, int]]:
        return [cls._MAPPING[col]["colspec"] for col in cls._MAPPING]

    @classmethod
    def get_column_names(cls) -> List[str]:
        return list(cls.get_mapping().keys())

    @classmethod
    def get_column_info(cls, column_name: str) -> Optional[Dict]:
        """Lấy thông tin chi tiết về cột"""
        return cls.get_mapping().get(column_name, None)





# ============================================================================
# REACH MAPPING (RCH)
# =============================================================================
class ReachMapping(SWATColumnMapping):

    _MAPPING = {
        'RCH': {'colspec': (6, 11), 'dtype': 'int', 'description': 'Reach number',
                  'unit': '-', 'category': 'identifier'},
        'GIS': {'colspec': (12, 20), 'dtype': 'int', 'description': 'GIS code',
                'unit': '-', 'category': 'identifier'},
        'MON': {'colspec': (21, 26), 'dtype': 'int', 'description': 'Month',
                'unit': '-', 'category': 'time'},
        'AREAkm2': {'colspec': (27, 38), 'dtype': 'float', 'description': 'Drainage area',
                    'unit': 'km²', 'category': 'area'},
        'FLOW_INcms': {'colspec': (39, 50), 'dtype': 'float', 'description': 'Flow into reach',
                       'unit': 'cms', 'category': 'hydrology'},
        'FLOW_OUTcms': {'colspec': (51, 62), 'dtype': 'float', 'description': 'Flow out of reach',
                        'unit': 'cms', 'category': 'hydrology'},
        'EVAPcms': {'colspec': (63, 74), 'dtype': 'float', 'description': 'Evaporation',
                    'unit': 'cms', 'category': 'hydrology'},
        'TLOSScms': {'colspec': (75, 86), 'dtype': 'float', 'description': 'Transmission losses',
                     'unit': 'cms', 'category': 'hydrology'},
        'SED_INtons': {'colspec': (87, 98), 'dtype': 'float', 'description': 'Sediment into reach',
                       'unit': 'tons', 'category': 'sediment'},
        'SED_OUTtons': {'colspec': (99, 110), 'dtype': 'float', 'description': 'Sediment out of reach',
                        'unit': 'tons', 'category': 'sediment'},
        'SEDCONCmg_L': {'colspec': (111, 122), 'dtype': 'float', 'description': 'Sediment concentration',
                        'unit': 'mg/L', 'category': 'sediment'},
        'ORGN_INkg': {'colspec': (123, 134), 'dtype': 'float', 'description': 'Organic nitrogen into reach',
                      'unit': 'kg', 'category': 'nitrogen'},
        'ORGN_OUTkg': {'colspec': (135, 146), 'dtype': 'float', 'description': 'Organic nitrogen out of reach',
                       'unit': 'kg', 'category': 'nitrogen'},
        'ORGP_INkg': {'colspec': (147, 158), 'dtype': 'float', 'description': 'Organic phosphorus into reach',
                      'unit': 'kg', 'category': 'phosphorus'},
        'ORGP_OUTkg': {'colspec': (159, 170), 'dtype': 'float', 'description': 'Organic phosphorus out of reach',
                       'unit': 'kg', 'category': 'phosphorus'},
        'NO3_INkg': {'colspec': (171, 182), 'dtype': 'float', 'description': 'Nitrate into reach',
                     'unit': 'kg', 'category': 'nitrogen'},
        'NO3_OUTkg': {'colspec': (183, 194), 'dtype': 'float', 'description': 'Nitrate out of reach',
                      'unit': 'kg', 'category': 'nitrogen'},
        'NH4_INkg': {'colspec': (195, 206), 'dtype': 'float', 'description': 'Ammonium into reach',
                     'unit': 'kg', 'category': 'nitrogen'},
        'NH4_OUTkg': {'colspec': (207, 218), 'dtype': 'float', 'description': 'Ammonium out of reach',
                      'unit': 'kg', 'category': 'nitrogen'},
        'NO2_INkg': {'colspec': (219, 230), 'dtype': 'float', 'description': 'Nitrite into reach',
                     'unit': 'kg', 'category': 'nitrogen'},
        'NO2_OUTkg': {'colspec': (231, 242), 'dtype': 'float', 'description': 'Nitrite out of reach',
                      'unit': 'kg', 'category': 'nitrogen'},
        'MINP_INkg': {'colspec': (243, 254), 'dtype': 'float', 'description': 'Mineral phosphorus into reach',
                      'unit': 'kg', 'category': 'phosphorus'},
        'MINP_OUTkg': {'colspec': (255, 266), 'dtype': 'float', 'description': 'Mineral phosphorus out of reach',
                       'unit': 'kg', 'category': 'phosphorus'},
        'TOT_Nkg': {'colspec': (543, 554), 'dtype': 'float', 'description': 'Total nitrogen',
                    'unit': 'kg', 'category': 'nitrogen'},
        'TOT_Pkg': {'colspec': (555, 566), 'dtype': 'float', 'description': 'Total phosphorus',
                    'unit': 'kg', 'category': 'phosphorus'},
        'WTMPdegc': {'colspec': (579, 590), 'dtype': 'float', 'description': 'Water temperature',
                     'unit': '°C', 'category': 'water_quality'},
    }

    @classmethod
    def get_mapping(cls) -> Dict:
        return cls._MAPPING



# HRU MAPPING
# Verified against output.hru from SWAT Rev 670 (VER 2018) and ch32_output.pdf
# Layout: LULC(4) HRU(5) GIS(10) SUB(5) MGT(5) MON(5) then 10-char columns,
#         except BACTP/BACTL which are 11-char each.
class HRUMapping(SWATColumnMapping):
    _MAPPING = {
        # ── Identifiers & time ──
        'LULC':     {'colspec': (0,   4),  'dtype': 'str',   'description': 'Land use/land cover code',
                     'unit': '-',     'category': 'identifier'},
        'HRU':      {'colspec': (4,   9),  'dtype': 'int',   'description': 'HRU number',
                     'unit': '-',     'category': 'identifier'},
        'GIS':      {'colspec': (9,  19),  'dtype': 'int',   'description': 'GIS code',
                     'unit': '-',     'category': 'identifier'},
        'SUB':      {'colspec': (19, 24),  'dtype': 'int',   'description': 'Subbasin number',
                     'unit': '-',     'category': 'identifier'},
        'MGT':      {'colspec': (24, 29),  'dtype': 'int',   'description': 'Management code',
                     'unit': '-',     'category': 'identifier'},
        'MON':      {'colspec': (29, 34),  'dtype': 'int',   'description': 'Month',
                     'unit': '-',     'category': 'time'},
        # ── Climate & water balance (10-char columns from pos 34) ──
        'AREAkm2':  {'colspec': (34,  44), 'dtype': 'float', 'description': 'HRU area',
                     'unit': 'km²',   'category': 'area'},
        'PRECIP':   {'colspec': (44,  54), 'dtype': 'float', 'description': 'Precipitation',
                     'unit': 'mm',    'category': 'climate'},
        'SNOFALL':  {'colspec': (54,  64), 'dtype': 'float', 'description': 'Snowfall',
                     'unit': 'mm',    'category': 'climate'},
        'SNOMELT':  {'colspec': (64,  74), 'dtype': 'float', 'description': 'Snow melt',
                     'unit': 'mm',    'category': 'climate'},
        'IRR':      {'colspec': (74,  84), 'dtype': 'float', 'description': 'Irrigation',
                     'unit': 'mm',    'category': 'water_management'},
        'PET':      {'colspec': (84,  94), 'dtype': 'float', 'description': 'Potential ET',
                     'unit': 'mm',    'category': 'hydrology'},
        'ET':       {'colspec': (94, 104), 'dtype': 'float', 'description': 'Actual ET',
                     'unit': 'mm',    'category': 'hydrology'},
        'SW_INIT':  {'colspec': (104, 114), 'dtype': 'float', 'description': 'Initial soil water',
                     'unit': 'mm',    'category': 'soil_water'},
        'SW_END':   {'colspec': (114, 124), 'dtype': 'float', 'description': 'Final soil water',
                     'unit': 'mm',    'category': 'soil_water'},
        'PERC':     {'colspec': (124, 134), 'dtype': 'float', 'description': 'Percolation',
                     'unit': 'mm',    'category': 'hydrology'},
        'GW_RCHG':  {'colspec': (134, 144), 'dtype': 'float', 'description': 'Groundwater recharge',
                     'unit': 'mm',    'category': 'groundwater'},
        'DA_RCHG':  {'colspec': (144, 154), 'dtype': 'float', 'description': 'Deep aquifer recharge',
                     'unit': 'mm',    'category': 'groundwater'},
        'REVAP':    {'colspec': (154, 164), 'dtype': 'float', 'description': 'Revap from shallow aquifer',
                     'unit': 'mm',    'category': 'groundwater'},
        'SA_IRR':   {'colspec': (164, 174), 'dtype': 'float', 'description': 'Shallow aquifer irrigation',
                     'unit': 'mm',    'category': 'water_management'},
        'DA_IRR':   {'colspec': (174, 184), 'dtype': 'float', 'description': 'Deep aquifer irrigation',
                     'unit': 'mm',    'category': 'water_management'},
        'SA_ST':    {'colspec': (184, 194), 'dtype': 'float', 'description': 'Shallow aquifer storage',
                     'unit': 'mm',    'category': 'groundwater'},
        'DA_ST':    {'colspec': (194, 204), 'dtype': 'float', 'description': 'Deep aquifer storage',
                     'unit': 'mm',    'category': 'groundwater'},
        'SURQ_GEN': {'colspec': (204, 214), 'dtype': 'float', 'description': 'Surface runoff generated',
                     'unit': 'mm',    'category': 'hydrology'},
        'SURQ_CNT': {'colspec': (214, 224), 'dtype': 'float', 'description': 'Surface runoff contribution',
                     'unit': 'mm',    'category': 'hydrology'},
        'TLOSS':    {'colspec': (224, 234), 'dtype': 'float', 'description': 'Transmission losses',
                     'unit': 'mm',    'category': 'hydrology'},
        'LATQ':     {'colspec': (234, 244), 'dtype': 'float', 'description': 'Lateral flow',
                     'unit': 'mm',    'category': 'hydrology'},
        'GW_Q':     {'colspec': (244, 254), 'dtype': 'float', 'description': 'Groundwater flow',
                     'unit': 'mm',    'category': 'groundwater'},
        'WYLD':     {'colspec': (254, 264), 'dtype': 'float', 'description': 'Water yield',
                     'unit': 'mm',    'category': 'hydrology'},
        'DAILYCN':  {'colspec': (264, 274), 'dtype': 'float', 'description': 'Curve number',
                     'unit': '-',     'category': 'hydrology'},
        # ── Temperature & radiation ──
        'TMP_AV':   {'colspec': (274, 284), 'dtype': 'float', 'description': 'Average temperature',
                     'unit': '°C',    'category': 'climate'},
        'TMP_MX':   {'colspec': (284, 294), 'dtype': 'float', 'description': 'Max temperature',
                     'unit': '°C',    'category': 'climate'},
        'TMP_MN':   {'colspec': (294, 304), 'dtype': 'float', 'description': 'Min temperature',
                     'unit': '°C',    'category': 'climate'},
        'SOL_TMP':  {'colspec': (304, 314), 'dtype': 'float', 'description': 'Soil temperature',
                     'unit': '°C',    'category': 'soil'},
        'SOLAR':    {'colspec': (314, 324), 'dtype': 'float', 'description': 'Solar radiation',
                     'unit': 'MJ/m²', 'category': 'climate'},
        # ── Sediment ──
        'SYLD':     {'colspec': (324, 334), 'dtype': 'float', 'description': 'Sediment yield',
                     'unit': 't/ha',  'category': 'sediment'},
        'USLE':     {'colspec': (334, 344), 'dtype': 'float', 'description': 'USLE soil loss',
                     'unit': 't/ha',  'category': 'sediment'},
        # ── Nutrient application & management ──
        'N_APP':    {'colspec': (344, 354), 'dtype': 'float', 'description': 'Nitrogen applied',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'P_APP':    {'colspec': (354, 364), 'dtype': 'float', 'description': 'Phosphorus applied',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'NAUTO':    {'colspec': (364, 374), 'dtype': 'float', 'description': 'Auto-applied nitrogen',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'PAUTO':    {'colspec': (374, 384), 'dtype': 'float', 'description': 'Auto-applied phosphorus',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'NGRZ':     {'colspec': (384, 394), 'dtype': 'float', 'description': 'Nitrogen from grazing',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'PGRZ':     {'colspec': (394, 404), 'dtype': 'float', 'description': 'Phosphorus from grazing',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'NCFRT':    {'colspec': (404, 414), 'dtype': 'float', 'description': 'Nitrogen from cont. fert.',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'PCFRT':    {'colspec': (414, 424), 'dtype': 'float', 'description': 'Phosphorus from cont. fert.',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'NRAIN':    {'colspec': (424, 434), 'dtype': 'float', 'description': 'Nitrogen in rainfall',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'NFIX':     {'colspec': (434, 444), 'dtype': 'float', 'description': 'Nitrogen fixation',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        # ── Nutrient cycling ──
        'F_MN':     {'colspec': (444, 454), 'dtype': 'float', 'description': 'Fresh org N to mineral N',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'A_MN':     {'colspec': (454, 464), 'dtype': 'float', 'description': 'Active org N to mineral N',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'A_SN':     {'colspec': (464, 474), 'dtype': 'float', 'description': 'Active to stable org N',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'F_MP':     {'colspec': (474, 484), 'dtype': 'float', 'description': 'Fresh org P to mineral P',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'AO_LP':    {'colspec': (484, 494), 'dtype': 'float', 'description': 'Active org to labile P',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'L_AP':     {'colspec': (494, 504), 'dtype': 'float', 'description': 'Labile to active mineral P',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'A_SP':     {'colspec': (504, 514), 'dtype': 'float', 'description': 'Active to stable mineral P',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'DNIT':     {'colspec': (514, 524), 'dtype': 'float', 'description': 'Denitrification',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'NUP':      {'colspec': (524, 534), 'dtype': 'float', 'description': 'Nitrogen uptake',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'PUP':      {'colspec': (534, 544), 'dtype': 'float', 'description': 'Phosphorus uptake',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        # ── Nutrient yields ──
        'ORGN':     {'colspec': (544, 554), 'dtype': 'float', 'description': 'Organic N yield',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'ORGP':     {'colspec': (554, 564), 'dtype': 'float', 'description': 'Organic P yield',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'SEDP':     {'colspec': (564, 574), 'dtype': 'float', 'description': 'Sediment P yield',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'NSURQ':    {'colspec': (574, 584), 'dtype': 'float', 'description': 'NO3 in surface runoff',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'NLATQ':    {'colspec': (584, 594), 'dtype': 'float', 'description': 'NO3 in lateral flow',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'NO3L':     {'colspec': (594, 604), 'dtype': 'float', 'description': 'NO3 leached',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'NO3GW':    {'colspec': (604, 614), 'dtype': 'float', 'description': 'NO3 in groundwater',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'SOLP':     {'colspec': (614, 624), 'dtype': 'float', 'description': 'Soluble P yield',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        'P_GW':     {'colspec': (624, 634), 'dtype': 'float', 'description': 'P in groundwater',
                     'unit': 'kg/ha', 'category': 'phosphorus'},
        # ── Stress factors ──
        'W_STRS':   {'colspec': (634, 644), 'dtype': 'float', 'description': 'Water stress days',
                     'unit': '-',     'category': 'stress'},
        'TMP_STRS': {'colspec': (644, 654), 'dtype': 'float', 'description': 'Temperature stress days',
                     'unit': '-',     'category': 'stress'},
        'N_STRS':   {'colspec': (654, 664), 'dtype': 'float', 'description': 'Nitrogen stress days',
                     'unit': '-',     'category': 'stress'},
        'P_STRS':   {'colspec': (664, 674), 'dtype': 'float', 'description': 'Phosphorus stress days',
                     'unit': '-',     'category': 'stress'},
        # ── Crop / biomass ──
        'BIOM':     {'colspec': (674, 684), 'dtype': 'float', 'description': 'Biomass',
                     'unit': 't/ha',  'category': 'crop'},
        'LAI':      {'colspec': (684, 694), 'dtype': 'float', 'description': 'Leaf area index',
                     'unit': '-',     'category': 'crop'},
        'YLD':      {'colspec': (694, 704), 'dtype': 'float', 'description': 'Yield',
                     'unit': 't/ha',  'category': 'crop'},
        # ── Bacteria (11-char columns) ──
        'BACTP':    {'colspec': (704, 715), 'dtype': 'float', 'description': 'Persistent bacteria',
                     'unit': '#/m²',  'category': 'bacteria'},
        'BACTL':    {'colspec': (715, 726), 'dtype': 'float', 'description': 'Less persistent bacteria',
                     'unit': '#/m²',  'category': 'bacteria'},
        # ── Water table, snow, carbon, tile drain (10-char columns) ──
        'WTAB_CLI': {'colspec': (726, 736), 'dtype': 'float', 'description': 'Water table depth (climate)',
                     'unit': 'm',     'category': 'groundwater'},
        'WTAB_SOL': {'colspec': (736, 746), 'dtype': 'float', 'description': 'Water table depth (soil)',
                     'unit': 'm',     'category': 'groundwater'},
        'SNO':      {'colspec': (746, 756), 'dtype': 'float', 'description': 'Snow water content',
                     'unit': 'mm',    'category': 'climate'},
        'CMUP':     {'colspec': (756, 766), 'dtype': 'float', 'description': 'Carbon uptake',
                     'unit': 'kg/ha', 'category': 'carbon'},
        'CMTOT':    {'colspec': (766, 776), 'dtype': 'float', 'description': 'Total carbon',
                     'unit': 'kg/ha', 'category': 'carbon'},
        'QTILE':    {'colspec': (776, 786), 'dtype': 'float', 'description': 'Tile drainage',
                     'unit': 'mm',    'category': 'drainage'},
        'TNO3':     {'colspec': (786, 796), 'dtype': 'float', 'description': 'Total NO3 in soil profile',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'LNO3':     {'colspec': (796, 806), 'dtype': 'float', 'description': 'NO3 leached below root zone',
                     'unit': 'kg/ha', 'category': 'nitrogen'},
        'GW_Q_D':   {'colspec': (806, 816), 'dtype': 'float', 'description': 'Groundwater flow to deep aq.',
                     'unit': 'mm',    'category': 'groundwater'},
        'LATQCNT':  {'colspec': (816, 826), 'dtype': 'float', 'description': 'Lateral flow contribution',
                     'unit': 'mm',    'category': 'hydrology'},
        'TVAP':     {'colspec': (826, 836), 'dtype': 'float', 'description': 'Total vaporization',
                     'unit': 'kg/ha', 'category': 'hydrology'},
    }
    @classmethod
    def get_mapping(cls) -> Dict:
        return cls._MAPPING




# SUBBASIN MAPPING (SUB)
class SubbasinMapping(SWATColumnMapping):
    _MAPPING = {
        'SUB': {'colspec': (7, 11), 'dtype': 'int', 'description': 'Subbasin number',
                'unit': '-', 'category': 'identifier'},
        'MON': {'colspec': (21, 25), 'dtype': 'int', 'description': 'Month',
                'unit': '-', 'category': 'time'},
        'AREAkm2': {'colspec': (26, 36), 'dtype': 'float', 'description': 'Subbasin area',
                    'unit': 'km²', 'category': 'area'},
        'PRECIP': {'colspec': (37, 45), 'dtype': 'float', 'description': 'Precipitation',
                   'unit': 'mm', 'category': 'climate'},
        'SNOMELT': {'colspec': (46, 55), 'dtype': 'float', 'description': 'Snow melt',
                    'unit': 'mm', 'category': 'climate'},
        'PET': {'colspec': (56, 65), 'dtype': 'float', 'description': 'Potential ET',
                'unit': 'mm', 'category': 'hydrology'},
        'ET': {'colspec': (66, 75), 'dtype': 'float', 'description': 'Actual ET',
               'unit': 'mm', 'category': 'hydrology'},
        'SW': {'colspec': (76, 85), 'dtype': 'float', 'description': 'Soil water',
               'unit': 'mm', 'category': 'soil_water'},
        'PERC': {'colspec': (86, 95), 'dtype': 'float', 'description': 'Percolation',
                 'unit': 'mm', 'category': 'hydrology'},
        'SURQ': {'colspec': (96, 105), 'dtype': 'float', 'description': 'Surface runoff',
                 'unit': 'mm', 'category': 'hydrology'},
        'GW_Q': {'colspec': (106, 115), 'dtype': 'float', 'description': 'Groundwater flow',
                 'unit': 'mm', 'category': 'groundwater'},
        'WYLD': {'colspec': (116, 125), 'dtype': 'float', 'description': 'Water yield',
                 'unit': 'mm', 'category': 'hydrology'},
        'SYLD': {'colspec': (126, 135), 'dtype': 'float', 'description': 'Sediment yield',
                 'unit': 't/ha', 'category': 'sediment'},
        'ORGN': {'colspec': (136, 145), 'dtype': 'float', 'description': 'Organic N yield',
                 'unit': 'kg/ha', 'category': 'nitrogen'},
        'ORGP': {'colspec': (146, 155), 'dtype': 'float', 'description': 'Organic P yield',
                 'unit': 'kg/ha', 'category': 'phosphorus'},
        'NSURQ': {'colspec': (156, 165), 'dtype': 'float', 'description': 'NO3 in surface runoff',
                  'unit': 'kg/ha', 'category': 'nitrogen'},
        'SOLP': {'colspec': (166, 175), 'dtype': 'float', 'description': 'Soluble P',
                 'unit': 'kg/ha', 'category': 'phosphorus'},
        'SEDP': {'colspec': (176, 185), 'dtype': 'float', 'description': 'Sediment P',
                 'unit': 'kg/ha', 'category': 'phosphorus'},
        'LATQ': {'colspec': (186, 195), 'dtype': 'float', 'description': 'Lateral flow',
                 'unit': 'mm', 'category': 'hydrology'},
        'GWNO3': {'colspec': (196, 205), 'dtype': 'float', 'description': 'NO3 in groundwater',
                  'unit': 'kg/ha', 'category': 'nitrogen'},
    }
    @classmethod
    def get_mapping(cls) -> Dict:
        return cls._MAPPING





# SUBBASIN MAPPING (SUB)
class WatoutMapping(SWATColumnMapping):
    _MAPPING =   {
        "YEAR":    {"colspec": (0, 5),   "dtype": "int",   "description": "Year",
                    "unit": "-",   "category": "time"},
        "DAY":     {"colspec": (6, 11),  "dtype": "int",   "description": "Day of year",
                    "unit": "-",   "category": "time"},
        "STEP":    {"colspec": (12, 17), "dtype": "int",   "description": "Step of simulated",
                    "unit": "-",   "category": "identifier"},
        "FLOW":    {"colspec": (18, 28), "dtype": "int",   "description": "Stream outlet flow",
                    "unit": "-",   "category": "identifier"}
        }
    @classmethod
    def get_mapping(cls) -> Dict:
        return cls._MAPPING

