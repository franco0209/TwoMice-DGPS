# TwoMice-DGPS

Caracterización de antena con VNA y GPS diferencial con dos Mighty Mouse 3GPS.
Curso: Comunicaciones Satelitales – Laboratorio C.

Descripción original del proyecto: [docs/Proyecto_2_Mighty_Mouse_GPS_VNA.md](docs/Proyecto_2_Mighty_Mouse_GPS_VNA.md)

## Estructura
- `backend/`: API FastAPI (VNA, adquisición NMEA, análisis diferencial)
- `frontend/`: React + Vite (pendiente)
- `data/`: archivos de ejemplo (`.s1p`, logs NMEA)

## Backend
```
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

## Hoja de ruta
- [x] Módulo VNA: parser Touchstone, S11/VSWR/Z, resonancias, bandas GNSS
- [ ] Frontend: carga de .s1p y gráficas S11/VSWR
- [ ] Adquisición NMEA de dos receptores
- [ ] Diferencial en dominio de posición y métricas (CEP, RMSE, 2DRMS)
- [ ] Informe PDF
