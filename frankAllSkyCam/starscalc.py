import cv2
import numpy as np

def analyze_sky_robust(image_path, diametro_rapporto=0.75, sensibilita=0.5, min_contrasto=25):
    """
    Analizza il cielo notturno per contare le stelle e stimare la copertura nuvolosa.
    
    INPUT:
    - image_path: percorso del file immagine
    - diametro_rapporto: dimensione della ROI circolare (0.1 - 1.0)
    - sensibilita: parametro per il filtro di circolarità e area (0.1 - 1.0)
    - min_contrasto: soglia minima di intensità per distinguere una stella dal rumore
    
    OUTPUT:
    - star_count: numero di stelle rilevate
    - cloud_cover: percentuale di copertura nuvolosa (0-100)
    """
    img = cv2.imread(image_path)
    if img is None:
        return 0, 100.0

    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Maschera Circolare Parametrica
    mask = np.zeros((height, width), dtype=np.uint8)
    radius = int((width * diametro_rapporto) / 2)
    center = (width // 2, height // 2)
    cv2.circle(mask, center, radius, 255, -1)

    # 2. Analisi Statistica ROI (Solo pixel nel cerchio)
    roi_pixels = gray[mask == 255]
    diff_contrasto = np.max(roi_pixels) - np.min(roi_pixels)
    std_dev = np.std(roi_pixels)

    # Inizializzazione output
    star_count = 0
    cloud_cover = 0.0

    # 3. FILTRO DI SICUREZZA: Se il cielo è troppo piatto, è coperto o buio pesto
    if diff_contrasto < min_contrasto:
        return 0, 100.0

    # 4. RILEVAMENTO STELLE
    # Top-hat per rimuovere gradienti lenti (nuvole/luna) e isolare i punti
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, 
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7,7)))
    
    # Soglia globale basata sul contrasto minimo per evitare falsi positivi da rumore
    _, thresh = cv2.threshold(tophat, min_contrasto, 255, cv2.THRESH_BINARY)
    thresh = cv2.bitwise_and(thresh, thresh, mask=mask)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Parametri dinamici basati sulla sensibilità
    circ_target = 0.4 + (sensibilita * 0.4) # Range 0.44 - 0.8
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 1.5 <= area <= 150:
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0: continue
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            
            if circularity > circ_target:
                star_count += 1
                # Disegno marker per debug visivo (opzionale)
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.drawMarker(img, (x + w//2, y + h//2), (0, 255, 0), cv2.MARKER_CROSS, 8, 1)

    # 5. CALCOLO COPERTURA NUVOLOSA
    # Logica: Più stelle ci sono, meno nuvole ci sono. 
    # Se ci sono poche stelle, la StdDev bassa conferma la presenza di nuvole uniformi.
    if star_count > 50:
        cloud_cover = 0.0
    else:
        # Calcolo empirico: meno stelle e meno varianza = più nuvole
        # std_dev tipica cielo sereno > 15, cielo coperto < 8
        cloud_cover = 100.0 - (star_count * 2.0) - (std_dev * 2.5)
        cloud_cover = max(0.0, min(100.0, cloud_cover))
        
        # Override per totale copertura
        if star_count == 0 and std_dev < 12:
            cloud_cover = 100.0

    # Generazione immagine di debug
    #cv2.circle(img, center, radius, (255, 0, 0), 2)
    #cv2.putText(img, f"STARS: {star_count} CLOUDS: {cloud_cover:.1f}%", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    #cv2.imwrite('debug_' + image_path, img)

    return star_count, round(cloud_cover, 1)

# Esempio di utilizzo:
#n_stelle, %_nuvole = 
analyze_sky_robust('sereno.jpg', 0.75, 0.5, 30)
analyze_sky_robust('sereno2.jpg', 0.75, 0.5, 30)
analyze_sky_robust('nuvoloso.jpg', 0.75, 0.5, 30)
analyze_sky_robust('parz_nuvoloso.jpg', 0.75, 0.5, 30)
analyze_sky_robust('luna.jpg', 0.75, 0.5, 30)
analyze_sky_robust('luna_dietro_nuvole.jpg', 0.75, 0.5, 30)
analyze_sky_robust('tutto_nuvoloso.jpg', 0.75, 0.5, 30)
analyze_sky_robust('sereno_buio.jpg', 0.75, 0.5, 30)