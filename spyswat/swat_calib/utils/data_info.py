from dataclasses import dataclass


@dataclass
class DATAParameter:
    """
    SWAT parameter definition
    Attributes:
        name: Parameter name (e.g., 'CN2')
        ext: File extension (e.g., 'hru', 'sol')
        line: Line number in file (0-indexed)
        start: Start column position
        end: End column position
        round: Number of decimal places
        vmin: Minimum allowed value
        vmax: Maximum allowed value
    """
    name: str
    ext: str
    line: int
    start: int
    end: int
    round: int
    vmin: float
    vmax: float


@dataclass
class HRUInfo:
    """
    HRU identification information
    Attributes:
        filename: HRU filename
        HRU: Watershed HRU ID
        Subbasin: Subbasin number
        HRU_Sub: HRU number within subbasin
        Luse: Land use code
        Soil: Soil type
        Slope: Slope class
    """
    filename: str
    HRU: int
    Subbasin: int
    HRU_Sub: int
    Luse: str
    Soil: str
    Slope: str

