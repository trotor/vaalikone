# Embedding-mallisuositukset

## Suomenkielinen poliittinen data — benchmarkatut tulokset

Testattu 15 kyselyllä (metsäpolitiikka, verotus, maahanmuutto, ilmasto, koulutus, sosiaaliturva, ydinvoima, NATO, terveydenhuolto, työllisyys, eläkkeet, asuminen, varjobudjetti, eutanasia, kannabis).

### Suositukset käyttötapauksen mukaan

#### Paras yleisvalinta: `ollama/bge-m3`
- **Keskiarvo**: 0.578 | **Voitot**: 12/15 | **Puoluekattavuus**: 11/16
- Ilmainen, lokaali, 100% vakaa, 1.2 GB
- Paras suomenkielinen ymmärrys lokaalimalleista
- **Käytä kun**: oletusvalinta kaikissa tilanteissa

#### Paras jos vain OpenAI käytettävissä: `text-embedding-3-small`
- **Keskiarvo**: 0.513 | **Puoluekattavuus**: 7/16
- Nopein (API-kutsu), 1536 dimensiota
- Heikompi suomenkielinen diversiteetti (kallistuu Vihreiden dokumentteihin)
- ~$0.01 koko tietokannan embeddaamiseen
- **Käytä kun**: ei Ollamaa, tarvitaan nopeus, hinta ei ongelma

#### Paras teoreettinen laatu: `ollama/mxbai-embed-large`
- **Keskiarvo**: 0.637 | **Voitot**: 10/15
- Korkein similarity-score, mutta **vain 5% dokumenteista embeddautui onnistuneesti**
- Kaatuu jatkuvasti Ollaman 500-virheisiin isommilla teksteillä
- **Käytä kun**: Ollama korjaa stabiliteetiongelmat tulevissa versioissa

#### Ei suositella suomeksi: `ollama/zembed-1`
- **Keskiarvo**: 0.486 | **Voitot**: 0/15
- 4B parametria, 2560 dimensiota, 2.5 GB — liian iso hyötyyn nähden
- Heikko suomenkielinen ymmärrys (englanninkielinen malli)
- Hidas: ~40 min koko tietokannalle
- CC BY-NC -lisenssi (ei-kaupallinen)

### Vertailutaulukko

| Malli | Dim | Koko | Avg sim | Voitot | Puolueet | Vakaus | Hinta |
|-------|-----|------|---------|--------|----------|--------|-------|
| **bge-m3** | 1024 | 1.2 GB | **0.578** | **12/15** | 11 | 100% | Ilmainen |
| mxbai-embed-large | 1024 | 669 MB | 0.637* | 10/15* | 8* | 5% | Ilmainen |
| text-embedding-3-small | 1536 | — | 0.513 | 2/15 | 7 | 100% | ~$0.01 |
| zembed-1 (Q4) | 2560 | 2.5 GB | 0.486 | 0/15 | 11 | 47% | Ilmainen |

\* mxbai: korkeat pisteet mutta epävakaa — vertailee vain pientä osadataa.

### Multi-model strategia

Tietokanta tukee useita embedding-malleja rinnakkain (`model_name`-kenttä).
Voit embeddauttaa saman datan usealla mallilla ja vertailla:

```bash
vaalikone ingest embed --model ollama/bge-m3
vaalikone ingest embed --model text-embedding-3-small
vaalikone compare-embeddings --models ollama/bge-m3,text-embedding-3-small
```

### Asennusohjeet (macOS)

```bash
# Ollama
brew install ollama
# tai: https://ollama.com/download

# Suositeltu embedding-malli
ollama pull bge-m3

# Vaihtoehtoiset
ollama pull mxbai-embed-large
ollama pull nomic-embed-text    # 274 MB, kevyin mutta heikoin suomeksi

# zembed-1 (GGUF, vaatii manuaalisen tuonnin)
# 1. Lataa: https://huggingface.co/Abhiray/zembed-1-Q4_K_M-GGUF
# 2. ollama create zembed-1 -f models/Modelfile.zembed-1
```
