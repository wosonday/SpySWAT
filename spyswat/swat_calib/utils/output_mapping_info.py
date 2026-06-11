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
class HRUMapping(SWATColumnMapping):
    _MAPPING = {
        'LULC': {'colspec': (0, 4), 'dtype': 'str', 'description': 'Land use/land cover code',
                 'unit': '-', 'category': 'identifier'},
        'HRU': {'colspec': (4, 8), 'dtype': 'int', 'description': 'HRU number',
                'unit': '-', 'category': 'identifier'},
        'GIS': {'colspec': (9, 17), 'dtype': 'int', 'description': 'GIS code',
                'unit': '-', 'category': 'identifier'},
        'SUB': {'colspec': (18, 22), 'dtype': 'int', 'description': 'Subbasin number',
                'unit': '-', 'category': 'identifier'},
        'MGT': {'colspec': (23, 27), 'dtype': 'int', 'description': 'Management code',
                'unit': '-', 'category': 'identifier'},
        'MON': {'colspec': (28, 32), 'dtype': 'int', 'description': 'Month',
                'unit': '-', 'category': 'time'},
        'AREAkm2': {'colspec': (32, 42), 'dtype': 'float', 'description': 'HRU area',
                    'unit': 'km²', 'category': 'area'},
        'PRECIP': {'colspec': (42, 52), 'dtype': 'float', 'description': 'Precipitation',
                   'unit': 'mm', 'category': 'climate'},
        'SNOFALL': {'colspec': (52, 62), 'dtype': 'float', 'description': 'Snowfall',
                    'unit': 'mm', 'category': 'climate'},
        'SNOMELT': {'colspec': (62, 72), 'dtype': 'float', 'description': 'Snow melt',
                    'unit': 'mm', 'category': 'climate'},
        'IRR': {'colspec': (72, 82), 'dtype': 'float', 'description': 'Irrigation',
                'unit': 'mm', 'category': 'water_management'},
        'PET': {'colspec': (82, 92), 'dtype': 'float', 'description': 'Potential ET',
                'unit': 'mm', 'category': 'hydrology'},
        'ET': {'colspec': (92, 102), 'dtype': 'float', 'description': 'Actual ET',
               'unit': 'mm', 'category': 'hydrology'},
        'SW_INIT': {'colspec': (102, 112), 'dtype': 'float', 'description': 'Initial soil water',
                    'unit': 'mm', 'category': 'soil_water'},
        'SW_END': {'colspec': (112, 122), 'dtype': 'float', 'description': 'Final soil water',
                   'unit': 'mm', 'category': 'soil_water'},
        'PERC': {'colspec': (122, 132), 'dtype': 'float', 'description': 'Percolation',
                 'unit': 'mm', 'category': 'hydrology'},
        'GW_RCHG': {'colspec': (132, 142), 'dtype': 'float', 'description': 'Groundwater recharge',
                    'unit': 'mm', 'category': 'groundwater'},
        'DA_RCHG': {'colspec': (142, 152), 'dtype': 'float', 'description': 'Deep aquifer recharge',
                    'unit': 'mm', 'category': 'groundwater'},
        'REVAP': {'colspec': (152, 162), 'dtype': 'float', 'description': 'Revap from shallow aquifer',
                  'unit': 'mm', 'category': 'groundwater'},
        'SA_ST': {'colspec': (182, 192), 'dtype': 'float', 'description': 'Shallow aquifer storage',
                  'unit': 'mm', 'category': 'groundwater'},
        'DA_ST': {'colspec': (192, 202), 'dtype': 'float', 'description': 'Deep aquifer storage',
                  'unit': 'mm', 'category': 'groundwater'},
        'SURQ_GEN': {'colspec': (202, 212), 'dtype': 'float', 'description': 'Surface runoff generated',
                     'unit': 'mm', 'category': 'hydrology'},
        'SURQ_CNT': {'colspec': (212, 222), 'dtype': 'float', 'description': 'Surface runoff contribution',
                     'unit': 'mm', 'category': 'hydrology'},
        'TLOSS': {'colspec': (222, 232), 'dtype': 'float', 'description': 'Transmission losses',
                  'unit': 'mm', 'category': 'hydrology'},
        'LATQ': {'colspec': (232, 242), 'dtype': 'float', 'description': 'Lateral flow',
                 'unit': 'mm', 'category': 'hydrology'},
        'GW_Q': {'colspec': (242, 252), 'dtype': 'float', 'description': 'Groundwater flow',
                 'unit': 'mm', 'category': 'groundwater'},
        'WYLD': {'colspec': (252, 262), 'dtype': 'float', 'description': 'Water yield',
                 'unit': 'mm', 'category': 'hydrology'},
        'DAILYCN': {'colspec': (262, 272), 'dtype': 'float', 'description': 'Curve number',
                    'unit': '-', 'category': 'hydrology'},
        'TMP_AV': {'colspec': (272, 282), 'dtype': 'float', 'description': 'Average temperature',
                   'unit': '°C', 'category': 'climate'},
        'TMP_MX': {'colspec': (282, 292), 'dtype': 'float', 'description': 'Max temperature',
                   'unit': '°C', 'category': 'climate'},
        'TMP_MN': {'colspec': (292, 302), 'dtype': 'float', 'description': 'Min temperature',
                   'unit': '°C', 'category': 'climate'},
        'SOL_TMP': {'colspec': (302, 312), 'dtype': 'float', 'description': 'Soil temperature',
                    'unit': '°C', 'category': 'soil'},
        'SOLAR': {'colspec': (312, 322), 'dtype': 'float', 'description': 'Solar radiation',
                  'unit': 'MJ/m²', 'category': 'climate'},
        'SYLD': {'colspec': (322, 332), 'dtype': 'float', 'description': 'Sediment yield',
                 'unit': 't/ha', 'category': 'sediment'},
        'USLE': {'colspec': (332, 342), 'dtype': 'float', 'description': 'USLE soil loss',
                 'unit': 't/ha', 'category': 'sediment'},
        'ORGN': {'colspec': (542, 552), 'dtype': 'float', 'description': 'Organic N yield',
                 'unit': 'kg/ha', 'category': 'nitrogen'},
        'ORGP': {'colspec': (552, 562), 'dtype': 'float', 'description': 'Organic P yield',
                 'unit': 'kg/ha', 'category': 'phosphorus'},
        'NSURQ': {'colspec': (572, 582), 'dtype': 'float', 'description': 'NO3 in surface runoff',
                  'unit': 'kg/ha', 'category': 'nitrogen'},
        'NLATQ': {'colspec': (582, 592), 'dtype': 'float', 'description': 'NO3 in lateral flow',
                  'unit': 'kg/ha', 'category': 'nitrogen'},
        'NO3L': {'colspec': (592, 602), 'dtype': 'float', 'description': 'NO3 leached',
                 'unit': 'kg/ha', 'category': 'nitrogen'},
        'NO3GW': {'colspec': (602, 612), 'dtype': 'float', 'description': 'NO3 in groundwater',
                  'unit': 'kg/ha', 'category': 'nitrogen'},
        'SOLP': {'colspec': (612, 622), 'dtype': 'float', 'description': 'Soluble P yield',
                 'unit': 'kg/ha', 'category': 'phosphorus'},
        'BIOM': {'colspec': (672, 682), 'dtype': 'float', 'description': 'Biomass',
                 'unit': 't/ha', 'category': 'crop'},
        'LAI': {'colspec': (682, 692), 'dtype': 'float', 'description': 'Leaf area index',
                'unit': '-', 'category': 'crop'},
        'YLD': {'colspec': (692, 702), 'dtype': 'float', 'description': 'Yield',
                'unit': 't/ha', 'category': 'crop'},
        'QTILE': {'colspec': (772, 782), 'dtype': 'float', 'description': 'Tile drainage',
                  'unit': 'mm', 'category': 'drainage'},
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

