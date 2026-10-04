import { combinedCredits } from '../services/api';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function ndviTrendFromFarm(farm) {
  const ndvi = parseFloat(farm.ndvi) || 0.45;
  const now = new Date();
  const currentMonth = now.getMonth();
  return MONTHS.map((month, i) => {
    const seasonal = Math.sin((i / 12) * Math.PI * 2) * 0.08;
    const historical = Math.max(0.2, Math.min(0.95, ndvi + seasonal - 0.04 + (i % 3) * 0.01));
    const forecastVal = Math.max(0.2, Math.min(0.95, ndvi + seasonal + 0.02));
    return {
      month: `${month} ${String(now.getFullYear()).slice(2)}`,
      historical: i <= currentMonth ? Number(historical.toFixed(2)) : null,
      forecast: i >= currentMonth ? Number(forecastVal.toFixed(2)) : null,
    };
  });
}

/** Map Supabase farm row → DetailedFarmAnalytics UI shape */
export function farmToAnalytics(farm, index = 0) {
  const ndvi = parseFloat(farm.ndvi) || 0;
  const credits = combinedCredits(farm);
  const soilMoisture = parseFloat(farm.soil_moisture) || 0;
  const aiConf = parseFloat(farm.ai_confidence) || 95;

  return {
    id: farm.id || `farm-${index}`,
    name: farm.name || 'My Farm',
    cropType: farm.crop_type || 'Mixed Crop',
    ndvi,
    vegetationHealth: farm.vegetation_health || (ndvi > 0.6 ? 'Good' : ndvi > 0.4 ? 'Moderate' : 'Sparse'),
    carbonPot: `${credits.total} t CO2e/yr`,
    soilCarbon: `${soilMoisture}% SOC`,
    aiConfidence: `${aiConf}%`,
    biodiversity: `${farm.biodiversity_score ?? 0}/100`,
    waterRetention: `${soilMoisture}%`,
    areaHectares: farm.area_hectares,
    ndviTrend: ndviTrendFromFarm(farm),
    scans: [
      {
        id: 1,
        source: farm.satellite_source || 'Google Earth Engine · Sentinel-2 SR',
        time: farm.created_at ? new Date(farm.created_at).toLocaleDateString() : 'Latest scan',
        label: `NDVI ${ndvi.toFixed(2)}`,
        type: 'success',
      },
    ],
  };
}

export function farmsToAnalytics(farms) {
  return (farms || []).map(farmToAnalytics);
}

/** Map marketplace listing → landing page auction card */
export function listingToAuction(listing) {
  const total =
    parseFloat(listing.total_credits) ||
    (parseFloat(listing.carbon_credits) || 0) + (parseFloat(listing.biodiversity_credits) || 0);
  const price = parseFloat(listing.price_per_credit) || 520;
  return {
    id: listing.id,
    crop: listing.crop || 'Carbon Credits',
    farmer: listing.farmer_name || 'Farmer',
    location: listing.location || '',
    credits: `${total.toFixed(1)} tCO2e`,
    currentBid: `₹${price}/credit`,
    image: listing.image_url || 'https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&q=80&w=400',
  };
}
