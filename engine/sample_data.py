"""
CiteMatch v2 测试数据生成工具
"""
import os

TEST_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

SAMPLE_BIB = """@article{Chen2023Flexible,
  author    = {Chen, Y. and Wang, L. and Zhang, H.},
  title     = {Flexible Piezoelectric Blood Pressure Sensor with High Sensitivity},
  journal   = {Advanced Materials},
  year      = {2023},
  volume    = {35},
  pages     = {2301234},
  doi       = {10.1002/adma.202301234}
}

@article{Wang2024Ultrathin,
  author    = {Wang, X. and Li, J. and Kim, S.},
  title     = {Ultrathin Conformal Piezoresistive Sensor Array for Continuous Blood Pressure Monitoring},
  journal   = {ACS Nano},
  year      = {2024},
  volume    = {18},
  pages     = {5678},
  doi       = {10.1021/acsnano.4c00123}
}

@article{Park2025Hyperspectral,
  author    = {Park, J. H. and Lee, S. M. and Choi, D.},
  title     = {Wearable Hyperspectral Photoplethysmography for Cuffless Blood Pressure Estimation},
  journal   = {Science Advances},
  year      = {2025},
  volume    = {11},
  pages     = {eadq7890},
  doi       = {10.1126/sciadv.adq7890}
}

@article{Tan2022PulseWave,
  author    = {Tan, P. and Ng, K. and Lim, W.},
  title     = {Pulse Wave Analysis Using Deep Learning for Non-Invasive Blood Pressure Measurement},
  journal   = {Nature Communications},
  year      = {2022},
  volume    = {13},
  pages     = {4567},
  doi       = {10.1038/s41467-022-34567-8}
}

@article{Liu2023Iontronic,
  author    = {Liu, Z. and Huang, Y. and Wu, F.},
  title     = {Iontronic Pressure Sensor with Ultrahigh Sensitivity for Wearable Health Monitoring},
  journal   = {Nature Nanotechnology},
  year      = {2023},
  volume    = {18},
  pages     = {890},
  doi       = {10.1038/s41565-023-01456-7}
}
"""

SAMPLE_DRAFT_EN = """# Wearable Blood Pressure Sensors: A Review

## Introduction

Flexible blood pressure sensors have attracted significant attention
in recent years. Chen et al. developed a piezoelectric sensor with
high sensitivity [1]. Wang et al. proposed an ultrathin piezoresistive
array for continuous monitoring [2].

## Methods

### Sensor Fabrication

The fabrication process follows the method described by Tan et al. [3].
Liu et al. introduced an iontronic approach with ultrahigh sensitivity [4].

### Signal Processing

| Method | Sensitivity | Response Time | Reference |
|--------|-------------|---------------|-----------|
| Piezoelectric | 15 mV/kPa | 10 ms | [1] |
| Piezoresistive | 8 mV/kPa | 25 ms | [2] |
| Iontronic | 50 mV/kPa | 5 ms | [4] |

## Results

Park et al. recently demonstrated a hyperspectral PPG approach
for cuffless BP estimation [5].

**References**

[1] Chen, Y., Wang, L., Zhang, H. (2023). Flexible Piezoelectric Blood
Pressure Sensor with High Sensitivity. *Advanced Materials*, 35, 2301234.

[2] Wang, X., Li, J., Kim, S. (2024). Ultrathin Conformal Piezoresistive
Sensor Array. *ACS Nano*, 18, 5678.

[3] Tan, P., Ng, K., Lim, W. (2022). Pulse Wave Analysis Using Deep
Learning. *Nature Communications*, 13, 4567.

[4] Liu, Z., Huang, Y., Wu, F. (2023). Iontronic Pressure Sensor with
Ultrahigh Sensitivity. *Nature Nanotechnology*, 18, 890.

[5] Park, J. H., Lee, S. M., Choi, D. (2025). Wearable Hyperspectral
Photoplethysmography. *Science Advances*, 11, eadq7890.
"""

SAMPLE_DRAFT_ZH = """# 可穿戴血压传感器综述

## 引言

近年来，柔性血压传感器引起了广泛关注。Chen等人开发了一种高灵敏度
压电传感器[@Chen2023Flexible]。Wang等人提出了一种用于连续监测的
超薄共形压阻阵列[@Wang2024Ultrathin]。

## 方法

### 传感器制备

制备过程遵循Tan等人描述的方法[@Tan2022PulseWave]。
Liu等人引入了具有超高灵敏度的离子电子方法[@Liu2023Iontronic]。

### 信号处理

| 方法 | 灵敏度 | 响应时间 | 参考文献 |
|------|--------|----------|----------|
| 压电式 | 15 mV/kPa | 10 ms | [@Chen2023Flexible] |
| 压阻式 | 8 mV/kPa | 25 ms | [@Wang2024Ultrathin] |
| 离子电子式 | 50 mV/kPa | 5 ms | [@Liu2023Iontronic] |

## 结果

Park等人最近展示了一种用于无袖带血压估计的高光谱PPG方法[@Park2025Hyperspectral]。

**参考文献**

[1] Chen, Y., et al. (2023). Flexible Piezoelectric Blood Pressure Sensor.
*Advanced Materials*, 35, 2301234.
"""


def save_sample_data(data_dir: str) -> dict:
    """保存样本数据到指定目录"""
    os.makedirs(data_dir, exist_ok=True)

    files = {}
    for name, content in [
        ("sample_references.bib", SAMPLE_BIB),
        ("sample_draft_en.md", SAMPLE_DRAFT_EN),
        ("sample_draft_zh.md", SAMPLE_DRAFT_ZH),
    ]:
        path = os.path.join(data_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        files[name] = path

    return files
