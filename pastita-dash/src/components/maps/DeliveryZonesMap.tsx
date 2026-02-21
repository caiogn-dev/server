import React, { useEffect, useRef, useState } from 'react';
import type { DeliveryZone, StoreLocation } from '../../services/delivery';

const HERE_API_KEY = import.meta.env.VITE_HERE_API_KEY || '';
const HERE_API_VERSION = '3.1';
const HERE_CORE_JS = `https://js.api.here.com/v3/${HERE_API_VERSION}/mapsjs-core.js`;
const HERE_SERVICE_JS = `https://js.api.here.com/v3/${HERE_API_VERSION}/mapsjs-service.js`;
const HERE_UI_JS = `https://js.api.here.com/v3/${HERE_API_VERSION}/mapsjs-ui.js`;
const HERE_EVENTS_JS = `https://js.api.here.com/v3/${HERE_API_VERSION}/mapsjs-mapevents.js`;
const HERE_UI_CSS = `https://js.api.here.com/v3/${HERE_API_VERSION}/mapsjs-ui.css`;

const DEFAULT_CENTER = { lat: -10.1847, lng: -48.3337 };
const COLORS = [
  { fill: 'rgba(114, 47, 55, 0.12)', stroke: '#722F37' },
  { fill: 'rgba(212, 175, 55, 0.12)', stroke: '#D4AF37' },
  { fill: 'rgba(76, 175, 80, 0.12)', stroke: '#4CAF50' },
  { fill: 'rgba(33, 150, 243, 0.10)', stroke: '#2196F3' },
  { fill: 'rgba(255, 87, 34, 0.10)', stroke: '#FF5722' },
];

let hereLoadPromise: Promise<void> | null = null;

const loadScript = (src: string) =>
  new Promise<void>((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(script);
  });

const loadCss = (href: string) =>
  new Promise<void>((resolve) => {
    if (document.querySelector(`link[href="${href}"]`)) {
      resolve();
      return;
    }
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.onload = () => resolve();
    document.head.appendChild(link);
  });

const ensureHereLoaded = async () => {
  if (hereLoadPromise) {
    return hereLoadPromise;
  }

  hereLoadPromise = (async () => {
    await loadScript(HERE_CORE_JS);
    await loadScript(HERE_SERVICE_JS);
    await loadScript(HERE_EVENTS_JS);
    await loadScript(HERE_UI_JS);
    await loadCss(HERE_UI_CSS);
  })();

  return hereLoadPromise;
};

type HereMapInstance = {
  map: any;
  behavior: any;
  ui: any;
  cleanup: () => void;
};

const createMap = (container: HTMLDivElement, center: { lat: number; lng: number }) => {
  const H = (window as any).H;
  const platform = new H.service.Platform({ apikey: HERE_API_KEY });
  const defaultLayers = platform.createDefaultLayers();
  const map = new H.Map(container, defaultLayers.vector.normal.map, {
    center,
    zoom: 13,
    pixelRatio: window.devicePixelRatio || 1,
  });
  const behavior = new H.mapevents.Behavior(new H.mapevents.MapEvents(map));
  const ui = H.ui.UI.createDefault(map, defaultLayers);
  const resizeHandler = () => map.getViewPort().resize();
  window.addEventListener('resize', resizeHandler);

  return {
    map,
    behavior,
    ui,
    cleanup: () => {
      window.removeEventListener('resize', resizeHandler);
      map.dispose();
    },
  };
};

export type DeliveryZonesMapProps = {
  storeLocation?: StoreLocation | null;
  zones?: DeliveryZone[];
  height?: string;
};

const DeliveryZonesMap: React.FC<DeliveryZonesMapProps> = ({
  storeLocation,
  zones = [],
  height = '320px',
}) => {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<HereMapInstance | null>(null);
  const objectsRef = useRef<any[]>([]);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    if (!HERE_API_KEY || !mapRef.current) {
      return undefined;
    }

    let active = true;

    ensureHereLoaded()
      .then(() => {
        if (!active || !mapRef.current || mapInstanceRef.current) return;
        mapInstanceRef.current = createMap(mapRef.current, DEFAULT_CENTER);
        setMapReady(true);
      })
      .catch(() => {
        // Ignore map load errors for now; UI will show fallback text.
      });

    return () => {
      active = false;
      if (mapInstanceRef.current) {
        mapInstanceRef.current.cleanup();
        mapInstanceRef.current = null;
      }
      objectsRef.current = [];
    };
  }, []);

  useEffect(() => {
    if (!mapReady || !mapInstanceRef.current) return;
    const H = (window as any).H;
    const { map } = mapInstanceRef.current;

    objectsRef.current.forEach((obj) => {
      try {
        map.removeObject(obj);
      } catch {
        // ignore
      }
    });
    objectsRef.current = [];

    if (storeLocation?.latitude && storeLocation?.longitude) {
      const storeMarker = new H.map.Marker({
        lat: storeLocation.latitude,
        lng: storeLocation.longitude,
      });
      map.addObject(storeMarker);
      objectsRef.current.push(storeMarker);
    }

    const sortedZones = [...zones].sort((a, b) => (a.max_km || 0) - (b.max_km || 0));
    sortedZones.forEach((zone, index) => {
      if (!storeLocation?.latitude || !storeLocation?.longitude) return;
      const maxKm = zone.max_km ?? zone.min_km;
      if (!maxKm) return;
      const color = COLORS[index % COLORS.length];
      const circle = new H.map.Circle(
        { lat: storeLocation.latitude, lng: storeLocation.longitude },
        maxKm * 1000,
        {
          style: {
            fillColor: color.fill,
            strokeColor: color.stroke,
            lineWidth: 2,
          },
        }
      );
      map.addObject(circle);
      objectsRef.current.push(circle);
    });

    if (storeLocation?.latitude && storeLocation?.longitude) {
      map.setCenter({ lat: storeLocation.latitude, lng: storeLocation.longitude }, true);
    }
  }, [mapReady, storeLocation, zones]);

  if (!HERE_API_KEY) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50" style={{ height }}>
        <span className="text-sm text-gray-500">Chave HERE nao configurada.</span>
      </div>
    );
  }

  return (
    <div ref={mapRef} className="w-full rounded-lg border border-gray-200 overflow-hidden" style={{ height }} />
  );
};

export default DeliveryZonesMap;
