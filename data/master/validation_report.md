# Laporan Validasi Master Wilayah Sulawesi Utara

Dibuat: 2026-10-25T12:17:20+00:00

## Jumlah wilayah

| Jenis | Hasil | Diharapkan |
|---|---:|---:|
| provinsi | 1 | 1 |
| kabupaten | 11 | 11 |
| kota | 4 | 4 |
| kecamatan | 171 | 171 |
| kelurahan | 332 | 332 |
| desa | 1507 | 1507 |

## Temuan kritis

- (tidak ada)

## Peringatan

- provinsi: 1 geometri tidak valid di sumber (nested shells/self-intersection; sudah diperbaiki di output kecuali --no-repair)
- provinsi: 1 centroid sumber berada di luar poligonnya sendiri (pakai lat/lng_titik_dalam untuk titik yang pasti di dalam)
- kab_kota: 6 geometri tidak valid di sumber (nested shells/self-intersection; sudah diperbaiki di output kecuali --no-repair)
- kab_kota: 3 centroid sumber berada di luar poligonnya sendiri (pakai lat/lng_titik_dalam untuk titik yang pasti di dalam)
- kecamatan: 8 geometri tidak valid di sumber (nested shells/self-intersection; sudah diperbaiki di output kecuali --no-repair)
- kecamatan: 14 centroid sumber berada di luar poligonnya sendiri (pakai lat/lng_titik_dalam untuk titik yang pasti di dalam)
- desa_kelurahan: 1 geometri tidak valid di sumber (nested shells/self-intersection; sudah diperbaiki di output kecuali --no-repair)
- desa_kelurahan: 114 centroid sumber berada di luar poligonnya sendiri (pakai lat/lng_titik_dalam untuk titik yang pasti di dalam)
- kecamatan: 1 poligon 50-90% luasnya di dalam induk (qa_flag=batas_tidak_presisi; akibat penyederhanaan)
- kecamatan: 12 pasangan saudara tumpang tindih >5%
- desa_kelurahan: 19 poligon <50% luasnya di dalam induk (qa_flag=periksa_lokasi; lihat validation_anomali.csv)
- desa_kelurahan: 330 poligon 50-90% luasnya di dalam induk (qa_flag=batas_tidak_presisi; akibat penyederhanaan)

## Detail

```json
{
  "selisih_nama_S1_vs_S3": {
    "jumlah": 0,
    "contoh": []
  },
  "kodepos": {
    "desa_kelurahan_dengan_kodepos": 1839,
    "kodepos_unik": 269,
    "kodepos_di_luar_95xxx": []
  },
  "kecamatan_dengan_>1_kodepos": 34,
  "geometri": {
    "provinsi": {
      "fitur": 1,
      "dengan_poligon": 1,
      "tidak_valid_di_sumber": 1,
      "tidak_valid_di_output": 0,
      "centroid_sumber_di_luar_poligon": 1,
      "bbox_di_luar_rentang_sulut": 0,
      "kode_tidak_valid_di_sumber": [
        "71"
      ],
      "contoh_centroid_luar": [
        "71"
      ]
    },
    "kab_kota": {
      "fitur": 15,
      "dengan_poligon": 15,
      "tidak_valid_di_sumber": 6,
      "tidak_valid_di_output": 0,
      "centroid_sumber_di_luar_poligon": 3,
      "bbox_di_luar_rentang_sulut": 0,
      "kode_tidak_valid_di_sumber": [
        "71.03",
        "71.04",
        "71.06",
        "71.09",
        "71.10",
        "71.72"
      ],
      "contoh_centroid_luar": [
        "71.04",
        "71.09",
        "71.11"
      ]
    },
    "kecamatan": {
      "fitur": 171,
      "dengan_poligon": 171,
      "tidak_valid_di_sumber": 8,
      "tidak_valid_di_output": 0,
      "centroid_sumber_di_luar_poligon": 14,
      "bbox_di_luar_rentang_sulut": 0,
      "kode_tidak_valid_di_sumber": [
        "71.03.09",
        "71.03.14",
        "71.06.07",
        "71.09.07",
        "71.10.01",
        "71.72.01",
        "71.72.04",
        "71.72.08"
      ],
      "contoh_centroid_luar": [
        "71.02.18",
        "71.03.11",
        "71.03.25",
        "71.04.05",
        "71.06.04"
      ]
    },
    "desa_kelurahan": {
      "fitur": 1839,
      "dengan_poligon": 1839,
      "tidak_valid_di_sumber": 1,
      "tidak_valid_di_output": 0,
      "centroid_sumber_di_luar_poligon": 114,
      "bbox_di_luar_rentang_sulut": 0,
      "kode_tidak_valid_di_sumber": [
        "71.06.07.2018"
      ],
      "contoh_centroid_luar": [
        "71.01.14.2004",
        "71.01.20.2007",
        "71.01.33.2012",
        "71.01.35.2007",
        "71.01.35.2009"
      ]
    }
  },
  "catatan_geometri_sumber": {
    "71": [
      "geometri tidak valid di sumber: Nested shells[123.25725 0.923551]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.03": [
      "geometri tidak valid di sumber: Nested shells[125.611326 3.544459]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.03.09": [
      "geometri tidak valid di sumber: Nested shells[125.571032 3.754942]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.03.14": [
      "geometri tidak valid di sumber: Nested shells[125.589421 3.611314]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.04": [
      "geometri tidak valid di sumber: Nested shells[126.772655 4.249869]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.06": [
      "geometri tidak valid di sumber: Nested shells[125.188355 1.799807]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.06.07": [
      "geometri tidak valid di sumber: Nested shells[125.188355 1.799807]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.06.07.2018": [
      "geometri tidak valid di sumber: Self-intersection[125.068491659922 1.54775221662179]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.09": [
      "geometri tidak valid di sumber: Nested shells[125.361362 2.104466]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.09.07": [
      "geometri tidak valid di sumber: Nested shells[125.361362 2.104466]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.10": [
      "geometri tidak valid di sumber: Nested shells[124.625151 0.709345]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.10.01": [
      "geometri tidak valid di sumber: Nested shells[124.625151 0.709345]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.72": [
      "geometri tidak valid di sumber: Nested shells[125.183274 1.424551]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.72.01": [
      "geometri tidak valid di sumber: Nested shells[125.205497 1.433264]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.72.04": [
      "geometri tidak valid di sumber: Nested shells[125.23888 1.480915]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ],
    "71.72.08": [
      "geometri tidak valid di sumber: Nested shells[125.262588 1.441977]",
      "diperbaiki: union bagian poligon + pembulatan 1e-6"
    ]
  },
  "containment": {
    "kab_kota": {
      "diperiksa": 15,
      "rata2_persen_luas_di_dalam_induk": 97.93,
      "min_persen": 92.04,
      "batas_tidak_presisi_(50-90persen)": 0,
      "periksa_lokasi_(<50persen)": 0,
      "terburuk": [
        [
          92.0,
          "71.09",
          "Kabupaten Kep. Siau Tagulandang Biaro"
        ],
        [
          94.9,
          "71.03",
          "Kabupaten Kepulauan Sangihe"
        ],
        [
          96.7,
          "71.04",
          "Kabupaten Kepulauan Talaud"
        ],
        [
          97.1,
          "71.72",
          "Kota Bitung"
        ],
        [
          97.2,
          "71.06",
          "Kabupaten Minahasa Utara"
        ],
        [
          97.4,
          "71.71",
          "Kota Manado"
        ],
        [
          98.3,
          "71.02",
          "Kabupaten Minahasa"
        ],
        [
          98.3,
          "71.08",
          "Kabupaten Bolaang Mongondow Utara"
        ]
      ]
    },
    "kecamatan": {
      "diperiksa": 171,
      "rata2_persen_luas_di_dalam_induk": 98.81,
      "min_persen": 88.73,
      "batas_tidak_presisi_(50-90persen)": 1,
      "periksa_lokasi_(<50persen)": 0,
      "terburuk": [
        [
          88.7,
          "71.71.04",
          "Wenang"
        ],
        [
          92.2,
          "71.71.06",
          "Sario"
        ],
        [
          92.2,
          "71.09.04",
          "Siau Timur Selatan"
        ],
        [
          92.5,
          "71.71.09",
          "Malalayang"
        ],
        [
          92.5,
          "71.71.05",
          "Tikala"
        ],
        [
          92.7,
          "71.71.02",
          "Tuminting"
        ],
        [
          93.0,
          "71.09.02",
          "Siau Barat"
        ],
        [
          93.9,
          "71.10.05",
          "Modayag Barat"
        ]
      ]
    },
    "desa_kelurahan": {
      "diperiksa": 1839,
      "rata2_persen_luas_di_dalam_induk": 93.83,
      "min_persen": 0.0,
      "batas_tidak_presisi_(50-90persen)": 330,
      "periksa_lokasi_(<50persen)": 19,
      "terburuk": [
        [
          0.0,
          "71.07.10.2006",
          "Tombatu Tiga Tengah"
        ],
        [
          1.6,
          "71.71.03.1005",
          "Ketang Baru"
        ],
        [
          13.1,
          "71.71.03.1009",
          "Ternate Tanjung"
        ],
        [
          16.5,
          "71.04.17.2006",
          "Moronge Selatan I"
        ],
        [
          22.1,
          "71.04.17.2003",
          "Moronge II"
        ],
        [
          22.6,
          "71.71.06.1005",
          "Titiwungan Utara"
        ],
        [
          28.7,
          "71.04.17.2004",
          "Moronge Selatan"
        ],
        [
          29.0,
          "71.07.10.2004",
          "Tombatu Dua Tengah"
        ]
      ]
    }
  },
  "overlap_saudara": {
    "kab_kota": {
      "pasangan_saling_tindih_>0.01%": 15,
      "pasangan_tindih_>5persen_luas_terkecil": 0,
      "terbesar": []
    },
    "kecamatan": {
      "pasangan_saling_tindih_>0.01%": 199,
      "pasangan_tindih_>5persen_luas_terkecil": 12,
      "terbesar": [
        [
          30.2,
          "71.71.06",
          "71.71.07"
        ],
        [
          14.5,
          "71.02.07",
          "71.02.19"
        ],
        [
          11.6,
          "71.02.10",
          "71.02.19"
        ],
        [
          11.2,
          "71.71.05",
          "71.71.07"
        ],
        [
          9.1,
          "71.71.06",
          "71.71.09"
        ],
        [
          7.8,
          "71.03.08",
          "71.03.17"
        ],
        [
          7.3,
          "71.71.02",
          "71.71.03"
        ],
        [
          7.2,
          "71.72.04",
          "71.72.07"
        ]
      ]
    },
    "desa_kelurahan": {
      "pasangan_saling_tindih_>0.01%": 972,
      "pasangan_tindih_>5persen_luas_terkecil": 0,
      "terbesar": []
    }
  },
  "cakupan_luas": {
    "kab_kota": {
      "induk_diperiksa": 1,
      "rasio_luas_anak_per_induk_min": 1.004,
      "median": 1.004,
      "max": 1.004
    },
    "kecamatan": {
      "induk_diperiksa": 15,
      "rasio_luas_anak_per_induk_min": 0.984,
      "median": 0.999,
      "max": 1.015
    },
    "desa_kelurahan": {
      "induk_diperiksa": 171,
      "rasio_luas_anak_per_induk_min": 0.832,
      "median": 1.002,
      "max": 1.231
    }
  },
  "luas_km2_approx": {
    "provinsi": 14514.9,
    "jumlah_kab_kota_terhitung": 14577.2,
    "catatan": "Luas dihitung dari poligon yang sudah disederhanakan; hanya untuk sanity check, bukan angka resmi."
  }
}
```
