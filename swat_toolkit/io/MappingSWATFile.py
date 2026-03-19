from typing import List


class SWATFileMapping:
    WATERSHED_MAPPING = {
        '.bsn': ['basins.bsn'],
        '.cio': ['file.cio'],
        '.fig': ['fig.fig'],
        '.atm': ['atmo.atm'],
        '.wwq': ['wwq.wwq'],
        '.dat': ['crop.dat', 'till.dat', 'pest.dat', 'fert.dat',
                 'urban.dat', 'plant.dat', 'sep.dat', 'pesthru.dat']
    }
    INDEXED_MAPPING = {
        '.pcp': 'pcp{}.pcp',  # pcp1.pcp, pcp2.pcp, ...
        '.tmp': 'tmp{}.tmp',  # tmp1.tmp, tmp2.tmp, ...
        '.wgn': 'wgn{}.wgn',  # wgn1.wgn, wgn2.wgn, ...
    }
    SUBBASIN_MAPPING = {
        '.sub': '{:09d}.sub',  # 000010001.sub
        '.rte': '{:09d}.rte',  # 000010001.rte
        '.pnd': '{:09d}.pnd',
        '.wus': '{:09d}.wus',
        '.sep': '{:09d}.sep',
        '.swq': '{:09d}.swq',
    }

    HRU_MAPPING = {
        '.hru': '{:09d}.hru',  # 000010001.hru
        '.mgt': '{:09d}.mgt',  # 000010001.mgt
        '.sol': '{:09d}.sol',
        '.chm': '{:09d}.chm',
        '.gw': '{:09d}.gw',
    }

    RESERVOIR_MAPPING = {
        '.res': '{:09d}.res',
        '.wtr': '{:09d}.wtr',
    }

    OUTPUT_MAPPING = {
        '.std': ['output.std', 'input.std'],
        '.rch': ['output.rch'],
        '.sub': ['output.sub'],
        '.hru': ['output.hru'],
        '.rsv': ['output.rsv'],
        '.sed': ['output.sed'],
        '.out': ['output.out'],
        '.fin': ['output.fin'],
        '.dat': ['watout.dat']
    }


    @staticmethod
    def _get_watershed_file(ext: str) -> List[str]:
        """Lấy tên file watershed level
        :arg
            ext: Extension (.bsn, .cio, etc.)
        >>> SWATFileMapping._get_watershed_file('.bsn')
        ['basins.bsn']
        >>> SWATFileMapping._get_watershed_file('.cio')
        ['file.cio']
        """
        return SWATFileMapping.WATERSHED_MAPPING.get(ext, [])


    @staticmethod
    def _get_indexed_file(ext: str, index: int) -> str:
        """Lấy tên file có index (pcp, tmp, wgn)
        Args:
            ext: Extension (.pcp, .tmp, etc.)
            index: Số thứ tự (1, 2, 3, ...)
        >>> SWATFileMapping._get_indexed_file('.pcp', 1)
        'pcp1.pcp'
        >>> SWATFileMapping._get_indexed_file('.tmp', 3)
        'tmp3.tmp'
        """
        template = SWATFileMapping.INDEXED_MAPPING.get(ext)
        return template.format(index) if template else ""


    @staticmethod
    def _get_subbasin_file(ext: str, subbasin_id: int) -> str:
        """Lấy tên file subbasin level
        Args:
            ext: Extension (.sub, .rte, etc.)
            subbasin_id: ID subbasin (vd: 10001, 20001)
        >>> SWATFileMapping._get_subbasin_file('.sub', 10001)
        '000010001.sub'
        >>> SWATFileMapping._get_subbasin_file('.rte', 20001)
        '000020001.rte'
        """
        template = SWATFileMapping.SUBBASIN_MAPPING.get(ext)
        return template.format(subbasin_id) if template else ""


    @staticmethod
    def _get_hru_file(ext: str, subbasin_num: int, hru_num: int) -> str:
        template = SWATFileMapping.HRU_MAPPING.get(ext)
        if template:
            hru_id = subbasin_num * 10000 + hru_num
            return template.format(hru_id)
        return template


    @staticmethod
    def _get_reservoir_file(ext: str, reservoir_id: int) -> str:
        """Lấy tên file reservoir
        Args:
            ext: Extension (res, wtr, etc.)
            reservoir_id: ID reservoir (vd: 1, 2, 3, ...)
        """
        template = SWATFileMapping.RESERVOIR_MAPPING.get(ext)
        return template.format(reservoir_id) if template else ""

    @staticmethod
    def _get_output_file(ext: str) -> List[str]:
        """Lấy tên output files
        :arg
            ext: Extension (std, rch, etc.)
        >>> SWATFileMapping._get_output_file('.std')
        ['output.std', 'input.std']
        """
        return SWATFileMapping.OUTPUT_MAPPING.get(ext, [])



if __name__ == "__main__":
    __import__("doctest").testmod()
