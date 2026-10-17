import React, { createContext, useState, useContext, useEffect, useCallback, useMemo } from 'react';

const LanguageContext = createContext();

// Complete, rich translation dictionary for English, Hindi, and Telugu
const translations = {
  en: {
    // General / Navigation
    home: "Home",
    farm: "Farm",
    market: "Market",
    wallet: "Wallet",
    support: "Support",
    logout: "Logout",
    phone: "Phone Number",
    otp: "OTP",
    aadhaar: "Aadhaar Number",
    state: "State",
    district: "District",
    village: "Village",
    upiId: "UPI ID / VPA",
    welcome: "Welcome",
    continue: "Continue",
    back: "Back",
    submit: "Submit",
    helpline: "Helpline",
    liveChat: "Live Chat Help",
    verified: "Verified",
    pending: "Pending",

    // Role Selection
    selectRole: "Select Your Profile Portal",
    selectRoleDesc: "Choose your workspace interface to interact with CarbonX's premium agritech ecosystem.",
    farmerRole: "Indian Farmer (Kisan)",
    farmerRoleDesc: "Register your land, visualize NDVI satellite metrics, and receive secure instant UPI carbon payouts.",
    corporateRole: "Corporate ESG Buyer",
    corporateRoleDesc: "Purchase high-fidelity verified carbon offsets, audit BRSR reports, and fund sustainable agroforestry.",
    adminRole: "ISRO / Govt Admin",
    adminRoleDesc: "Audit satellite anomaly flags, review drone KYC submissions, and monitor blockchain carbon minting.",

    // Login
    loginWelcome: "Welcome Back",
    loginDesc: "Login to view carbon sequestration status and earnings.",
    registeredPhone: "Registered Phone Number",
    enterOtp: "Enter 4-Digit OTP",
    changePhone: "Change Phone Number",
    sendOtp: "Send OTP",
    loginBtn: "Login",
    firstTime: "First time using CarbonX?",
    registerFarmProfile: "Register Farm Profile 🌾",

    // Register
    verifyMobile: "Verify Mobile",
    verifyMobileDesc: "Enter your mobile number to receive a secure OTP.",
    preferredLang: "Preferred Language",
    farmlandProfile: "Farmland Profile",
    aadhaarDesc: "Establish identity verification mapping for carbon audits.",
    fullName: "Full Name (as in Aadhaar)",
    aadhaarNumber: "Aadhaar Number (UID)",
    verifyAadhaar: "Verify Aadhaar & Continue",
    directBank: "Direct Bank Payouts",
    bankDesc: "Establish linked UPI / Aadhaar-enabled bank ledger for payout credit.",
    bankInfo: "This matches the account details for instant carbon deposits.",
    upiSecured: "UPI payout setup secures instantaneous settlement immediately after global carbon buyers purchase your verified credits.",
    linkAccount: "Link Account & Complete KYC",
    profileVerified: "Profile Verified",
    profileVerifiedDesc: "Congratulations Ramesh Kumar! Your Aadhaar identity and bank payouts are fully verified. You are now ready to map your farm plot.",
    startTutorial: "Start Welcome Tutorial",

    // Onboarding/Tutorial
    tutorialTitle: "Satellite Soil Verification",
    tutorialDesc: "NASA and ISRO multi-spectral satellite imagery scans your soil organic carbon density without requiring manual soil collection.",
    tutorialTitle2: "UPI Wallet Settlements",
    tutorialDesc2: "Once carbon credits are verified and minted, funds are wired directly into your bank account via instant UPI.",
    tutorialTitle3: "Real-time NDVI Monitoring",
    tutorialDesc3: "Access high-resolution vegetation health charts, temperature indices, and biodiversity alerts right on your phone.",
    getStarted: "Get Started Mapping",

    // Farm Map
    bhuvanGeoportal: "Bhuvan Geoportal | 2D Viewer",
    nasaIsroLive: "NASA/ISRO LIVE",
    drawTool: "Draw Tool",
    measureArea: "Measure Area",
    cadastralBoundary: "Cadastral Boundary",
    enterCity: "Enter City or Lat,Lon (ex: Warangal or 17.9,79.5)",
    baseLayer: "Base Layer",
    satelliteMap: "Satellite Map",
    ndviIndex: "NDVI Index",
    soilMoisture: "Soil Moisture",
    terrainMap: "Terrain Map",
    calculatedArea: "Calculated Area",
    nodesPlotted: "Nodes Plotted",
    socDensity: "SOC Density",
    carbonValueEst: "Carbon Value Est.",
    tapToPlot: "Tap on the satellite layout above to plot your boundary nodes!",
    plotMore: "Plot at least 3 nodes to form a boundary...",
    boundaryClosed: "Boundary closed! Dynamic area: ",
    syncArea: "Sync Area",
    startPlotting: "Start Plotting",
    gpsLocating: "GPS Locked on Ramesh Kumar's plot: Venkateshwara Pally, Warangal.",

    // Dashboard
    activeFarms: "Active Verified Farms",
    upiWalletBalance: "UPI Wallet Balance",
    carbonSequestration: "Carbon Sequestration",
    activeContracts: "Active Smart Contracts",
    withdrawFunds: "Withdraw Funds",
    blockchainCert: "Blockchain ERC-1155 Ledger",
    viewCertificate: "View Certificate",
    creditsMinted: "Credits Minted",
    payoutHistory: "Payout & Activity History",
    recentSync: "Recent satellite sync completed.",
    biodiversityIndex: "Biodiversity Score",
    nitrogenLevels: "Soil Nitrogen Density",

    // Farm Analytics
    multiSpectral: "Multi-Spectral Satellite Analytics",
    farmHealthDashboard: "Farm Health & Sequestration Forecast",
    sequestrationTrend: "Carbon Sequestration Projection (tCO2e)",
    vegHealthIndex: "Vegetation Health (NDVI) Historical Graph",
    greenAiRec: "Green AI Agronomic Recommendations",
    aiRecText1: "Nitrogen levels are highly optimal. Transition to direct seeded rice to save 30% water and capture an additional 2.5 carbon credits/Ha.",
    aiRecText2: "NDVI shows strong photosynthetic density. Organic compost layer additions are recommended to enhance soil moisture retention.",
    anomaliesLog: "Satellite Anomaly & Compliance Logs",
    noAnomalies: "All scans compliant. 0 anomalies detected in the last 90 days.",

    dashGreeting: "Namaste",
    carbonLabel: "Carbon",
    bioLabel: "Biodiversity",
    combinedLabel: "Combined",
    farmsMapped: "farms mapped",
    noFarmsYet: "No farms yet. Draw your boundary on the GEE map and run satellite analysis.",
    mapFarmGee: "Map farm (GEE)",
    mapFarmDesc: "Satellite + draw boundary",
    marketplaceTitle: "Marketplace",
    marketplaceDesc: "Sell combined credits",
    listOnChain: "List credits on blockchain",
    marketPageTitle: "CarbonX Marketplace",
    marketPageSubtitle: "Verified carbon + biodiversity credits",
    searchFarmer: "Search farmer or location…",
    listMyCredits: "List my credits",
    loadingListings: "Loading listings…",
    noListings: "No listings yet. Farmers can list after GEE farm scan.",
    buyBid: "Buy / Bid",
    bidPlaced: "Bid placed",
    onChain: "On-chain",
    chainOffline: "Chain offline",
    geeMapTitle: "GEE Satellite Farm Mapping",
    geeMapDesc: "Search places by name, draw your boundary, then run Earth Engine analysis.",
    scanAi: "Scan AI",
    scanning: "Scanning…",
    savePlot: "Save Plot",
    saving: "Saving…",
    analysisComplete: "Satellite Analysis Complete",
    drawFirst: "Please draw your farm boundary on the map first.",
    loginRequired: "Please log in to save your farm.",
    backendDown: "Could not reach the server. Ensure the Python API is running.",
    smsSent: "OTP sent via SMS to +91",
    invalidPhone: "Enter a valid 10-digit number",
    enterOtp6: "Enter the 6-digit OTP",
    resendIn: "Resend in",
    resendOtp: "Resend OTP",
    serverError: "Server error. Please try again.",
    farmDetailsTitle: "Farmland Details",
    farmDetailsDesc: "Saved to your profile and used for credit verification.",
    cropType: "Crop Type",
    irrigationType: "Irrigation Type",
    soilType: "Soil Type",
    saveContinue: "Save & Continue",
    listingLive: "Listing live",
    listCombined: "List combined credits",
    verifiedBalance: "Your verified balance",
    creditsToList: "Credits to list (combined tCO2e)",
    pricePerCredit: "Price per credit (₹)",
    mintAndList: "Mint & list on marketplace",
    processing: "Processing…",
    mintSuccess: "Minted token",
    chainRequired: "Blockchain is not connected. Start Hardhat and set contract addresses in backend/.env.",
    otpFailed: "Failed to send OTP",
    areaLabel: "Area",
    mapped: "Mapped",
    credits: "Credits",
    totalCredits: "Total credits",
    score: "Score",
    canopy: "Canopy",
    accuracy: "Accuracy",
    liveGps: "Live GPS",

    // Layout & Navigation additions
    dashboard: "Dashboard",
    landVerification: "Land Verification",
    carbonPassport: "Carbon Passport",
    creditPooling: "Credit Pooling",
    esgDashboard: "ESG Dashboard",
    fpoDashboard: "FPO Dashboard",
    adminDashboard: "Admin Dashboard",
    adminCompliance: "Admin Compliance",
    bulkAutoMatch: "Bulk Auto-Match",
    certificates: "Certificates",
    fpoAuditDesk: "FPO Audit Desk",
    fpoDesk: "FPO Desk",
    walletLedger: "Wallet & UPI Ledger",
    notifications: "Notifications",
    noNotifications: "No notifications yet",
    login: "Login",

    // Tutorial additions
    skip: "Skip",
    step: "Step",
    of: "of",
    completed: "Completed",
    tutorialNavHint: "Use left/right arrow keys or buttons to navigate",
    restartTutorial: "Restart walkthrough",
    nextStep: "Next Step",
    proceedToFarm: "Proceed to My Farm",

    // Role Selection additions
    backToGateway: "Back to Gateway",
    roleAccessPortal: "Role-Based Access Portal",
    selectEcosystemRole: "Select Ecosystem Role",
    selectRoleSubtitle: "Choose your role to access customized dashboards, verification workflows, and marketplace portals.",
    enterPortal: "Enter Portal",
    farmerLandOwner: "Farmer & Land Owner",
    farmerLandOwnerDesc: "Register farm parcels via Telugu/Hindi/English voice input, upload land deeds for AI verification, and receive direct UPI carbon credit payouts.",
    fpoOfficer: "FPO / Cooperative Officer",
    fpoOfficerDesc: "Manage member farmers, perform bulk direct onboarding, inspect flagged ground-truth records, and execute cooperative credit pooling.",
    corporateBuyer: "Corporate Buyer & ESG Officer",
    corporateBuyerDesc: "Browse verified carbon credit listings, run bulk auto-match allocation algorithms, and manage Scope 1-3 retirement certificates.",

    // Voice & Registration additions
    voicePrompt: "Please enter your legal full name, mobile number, and identity details to enroll.",
    voiceNotSupported: "Voice input is not supported in this browser. Please type your details.",
    voiceCaptureError: "Could not capture your voice. Please type your details.",
    voiceDeviceError: "Could not start voice input on this device. Please type your details.",
    phoneOtpVerification: "Phone OTP Verification",
    enter6DigitCode: "Enter 6-Digit Code",
    resendCode: "Resend Code",
    resendingCode: "Resending…",
    didntReceiveCode: "Didn't receive code?",
    cancel: "Cancel",
    verifyAndRoute: "Verify & Route",
    codeDispatchedTo: "A 6-digit authentication code has been dispatched to",

    // Farmland & Dashboard additions
    enrollFirstParcel: "Enroll Your First Parcel",
    switchFarm: "Switch Farm:",
    selectedLandParcel: "Selected Land Parcel:",
    noFarmsEnrolled: "No farms enrolled yet",
    monitoringFlagged: "Monitoring Flagged",
    fpoInspected: "FPO Inspected Record"
  },
  hi: {
    // General / Navigation
    home: "मुख्य पृष्ठ",
    farm: "खेत",
    market: "बाज़ार",
    wallet: "बटुआ (वॉलेट)",
    support: "सहायता",
    logout: "लॉगआउट",
    phone: "फ़ोन नंबर",
    otp: "ओटीपी",
    aadhaar: "आधार नंबर",
    state: "राज्य",
    district: "ज़िला",
    village: "गाँव",
    upiId: "यूपीआई आईडी / वीपीए",
    welcome: "स्वागत हे",
    continue: "जारी रखें",
    back: "पीछे जाएँ",
    submit: "जमा करें",
    helpline: "हेल्पलाइन",
    liveChat: "लाइव चैट सहायता",
    verified: "सत्यापित",
    pending: "लंबित",

    // Role Selection
    selectRole: "अपना प्रोफ़ाइल पोर्टल चुनें",
    selectRoleDesc: "कार्बनएक्स (CarbonX) के प्रीमियम कृषि-तकनीक पारिस्थितिकी तंत्र के साथ बातचीत करने के लिए अपना इंटरफ़ेस चुनें।",
    farmerRole: "भारतीय किसान (Kisan)",
    farmerRoleDesc: "अपनी भूमि पंजीकृत करें, एनडीवीआई (NDVI) उपग्रह मेट्रिक्स देखें, और त्वरित यूपीआई कार्बन भुगतान प्राप्त करें।",
    corporateRole: "कॉर्पोरेट ईएसजी खरीदार",
    corporateRoleDesc: "सत्यापित कार्बन क्रेडिट खरीदें, बीआरएसआर रिपोर्ट ऑडिट करें, और स्थायी कृषि-वानिकी को वित्तपोषित करें।",
    adminRole: "इसरो / सरकारी व्यवस्थापक",
    adminRoleDesc: "उपग्रह विसंगति झंडों का ऑडिट करें, ड्रोन केवाईसी प्रविष्टियों की समीक्षा करें, और ब्लॉकचेन कार्बन मिंटिंग की निगरानी करें।",

    // Login
    loginWelcome: "आपका फिर से स्वागत है",
    loginDesc: "कार्बन संचय की स्थिति और अपनी कमाई देखने के लिए लॉगिन करें।",
    registeredPhone: "पंजीकृत फ़ोन नंबर",
    enterOtp: "4-अंकों का ओटीपी दर्ज करें",
    changePhone: "फ़ोन नंबर बदलें",
    sendOtp: "ओटीपी भेजें",
    loginBtn: "लॉगिन करें",
    firstTime: "कार्बनएक्स पर पहली बार आए हैं?",
    registerFarmProfile: "नया खेत प्रोफ़ाइल पंजीकृत करें 🌾",

    // Register
    verifyMobile: "मोबाइल नंबर सत्यापित करें",
    verifyMobileDesc: "एक सुरक्षित ओटीपी प्राप्त करने के लिए अपना मोबाइल नंबर दर्ज करें।",
    preferredLang: "पसंदीदा भाषा",
    farmlandProfile: "कृषि भूमि प्रोफ़ाइल",
    aadhaarDesc: "कार्बन ऑडिट के लिए पहचान सत्यापन मैपिंग स्थापित करें।",
    fullName: "पूरा नाम (आधार के अनुसार)",
    aadhaarNumber: "आधार नंबर (UID)",
    verifyAadhaar: "आधार सत्यापित करें और आगे बढ़ें",
    directBank: "सीधे बैंक में भुगतान",
    bankDesc: "भुगतान प्राप्त करने के लिए लिंक की गई यूपीआई / आधार-सक्षम बैंक खाता स्थापित करें।",
    bankInfo: "यह त्वरित कार्बन जमा के लिए बैंक खाते के विवरण से मेल खाता है।",
    upiSecured: "वैश्विक कार्बन खरीदारों द्वारा आपके सत्यापित क्रेडिट खरीदने के तुरंत बाद यूपीआई भुगतान सेटअप त्वरित निपटान सुरक्षित करता है।",
    linkAccount: "खाता लिंक करें और केवाईसी पूरा करें",
    profileVerified: "प्रोफ़ाइल सत्यापित हो गई",
    profileVerifiedDesc: "बधाई हो रमेश कुमार! आपकी आधार पहचान और बैंक भुगतान विवरण पूरी तरह से सत्यापित हो गए हैं। अब आप अपने खेत का नक्शा बनाने के लिए तैयार हैं।",
    startTutorial: "स्वागत ट्यूटोरियल शुरू करें",

    // Onboarding/Tutorial
    tutorialTitle: "सैटेलाइट मृदा सत्यापन",
    tutorialDesc: "नासा और इसरो के मल्टी-स्पेक्ट्रल उपग्रह चित्र आपकी मिट्टी के जैविक कार्बन घनत्व को मैन्युअल रूप से मिट्टी एकत्र किए बिना स्कैन करते हैं।",
    tutorialTitle2: "यूपीआई वॉलेट भुगतान",
    tutorialDesc2: "एक बार कार्बन क्रेडिट सत्यापित और मिंट हो जाने के बाद, धनराशि तुरंत यूपीआई के माध्यम से सीधे आपके बैंक खाते में भेज दी जाती है।",
    tutorialTitle3: "रीअल-टाइम एनडीवीआई निगरानी",
    tutorialDesc3: "उच्च-रिज़ॉल्यूशन वनस्पति स्वास्थ्य चार्ट, तापमान सूचकांक और जैव विविधता अलर्ट सीधे अपने फ़ोन पर प्राप्त करें।",
    getStarted: "नक्शा बनाना शुरू करें",

    // Farm Map
    bhuvanGeoportal: "भुवन जियोपोर्टल | 2डी व्यूअर",
    nasaIsroLive: "नासा/इसरो लाइव",
    drawTool: "ड्रॉ टूल (रेखांकन)",
    measureArea: "क्षेत्र मापें",
    cadastralBoundary: "कैडस्ट्रल (भू-कर) सीमा",
    enterCity: "शहर या अक्षांश,देशांतर दर्ज करें (उदा: वारंगल या 17.9,79.5)",
    baseLayer: "मुख्य परत",
    satelliteMap: "सैटेलाइट मैप",
    ndviIndex: "NDVI (वनस्पति) सूचकांक",
    soilMoisture: "मिट्टी की नमी",
    terrainMap: "धरातल (Terrain) नक्शा",
    calculatedArea: "परिकलित क्षेत्रफल",
    nodesPlotted: "चिह्नित बिंदु",
    socDensity: "मिट्टी कार्बन सूचकांक (SOC)",
    carbonValueEst: "अनुमानित कार्बन मूल्य",
    tapToPlot: "अपने खेत की सीमा के बिंदुओं को चिह्नित करने के लिए ऊपर सैटेलाइट मानचित्र पर टैप करें!",
    plotMore: "सीमा बनाने के लिए कम से कम 3 बिंदुओं को चिह्नित करें...",
    boundaryClosed: "सीमा पूरी हुई! वास्तविक क्षेत्रफल: ",
    syncArea: "क्षेत्रफल सिंक करें",
    startPlotting: "रेखांकन शुरू करें",
    gpsLocating: "रमेश कुमार के खेत पर जीपीएस लॉक: वेंकटेश्वर पल्ली, वारंगल।",

    // Dashboard
    activeFarms: "सक्रिय सत्यापित खेत",
    upiWalletBalance: "यूपीआई वॉलेट बैलेंस",
    carbonSequestration: "कार्बन संचय मात्रा",
    activeContracts: "सक्रिय स्मार्ट अनुबंध (Contracts)",
    withdrawFunds: "पैसे निकालें",
    blockchainCert: "ब्लॉकचेन ERC-1155 खाता",
    viewCertificate: "प्रमाणपत्र देखें",
    creditsMinted: "मिंट किए गए क्रेडिट",
    payoutHistory: "भुगतान और गतिविधि इतिहास",
    recentSync: "हाल ही में उपग्रह सिंक पूरा हुआ।",
    biodiversityIndex: "जैव विविधता स्कोर",
    nitrogenLevels: "मिट्टी में नाइट्रोजन घनत्व",

    // Farm Analytics
    multiSpectral: "मल्टी-स्पेक्ट्रल सैटेलाइट विश्लेषण",
    farmHealthDashboard: "खेत का स्वास्थ्य और कार्बन संचय पूर्वानुमान",
    sequestrationTrend: "अनुमानित कार्बन संचय (tCO2e)",
    vegHealthIndex: "वनस्पति स्वास्थ्य (NDVI) ऐतिहासिक ग्राफ",
    greenAiRec: "ग्रीन एआई (Green AI) कृषि सुझाव",
    aiRecText1: "नाइट्रोजन का स्तर बहुत उत्तम है। 30% पानी बचाने और अतिरिक्त 2.5 कार्बन क्रेडिट/हेक्टेयर प्राप्त करने के लिए सीधी बुवाई वाले धान की ओर बढ़ें।",
    aiRecText2: "NDVI मजबूत प्रकाश संश्लेषक घनत्व दिखाता है। मिट्टी में नमी बनाए रखने के लिए जैविक खाद की परतें जोड़ने की सिफारिश की जाती है।",
    anomaliesLog: "उपग्रह विसंगति और अनुपालन लॉग",
    noAnomalies: "सभी उपग्रह स्कैन अनुपालन में हैं। पिछले 90 दिनों में कोई विसंगति नहीं पाई गई।",

    dashGreeting: "नमस्ते",
    carbonLabel: "कार्बन",
    bioLabel: "जैव विविधता",
    combinedLabel: "संयुक्त",
    farmsMapped: "खेत मैप किए",
    noFarmsYet: "अभी कोई खेत नहीं। GEE मानचित्र पर सीमा बनाएं और उपग्रह विश्लेषण चलाएं।",
    mapFarmGee: "खेत मैप (GEE)",
    mapFarmDesc: "उपग्रह + सीमा बनाएं",
    marketplaceTitle: "बाज़ार",
    marketplaceDesc: "संयुक्त क्रेडिट बेचें",
    listOnChain: "ब्लॉकचेन पर सूचीबद्ध करें",
    marketPageTitle: "CarbonX बाज़ार",
    marketPageSubtitle: "सत्यापित कार्बन + जैव विविधता क्रेडिट",
    searchFarmer: "किसान या स्थान खोजें…",
    listMyCredits: "मेरे क्रेडिट सूचीबद्ध करें",
    loadingListings: "सूचियाँ लोड हो रही हैं…",
    noListings: "अभी कोई सूची नहीं।",
    buyBid: "खरीदें / बोली",
    bidPlaced: "बोली लगाई",
    onChain: "चेन पर",
    chainOffline: "चेन ऑफ़लाइन",
    geeMapTitle: "GEE उपग्रह खेत मैपिंग",
    geeMapDesc: "स्थान खोजें, सीमा बनाएं, फिर Earth Engine विश्लेषण चलाएं।",
    scanAi: "AI स्कैन",
    scanning: "स्कैन हो रहा…",
    savePlot: "प्लॉट सहेजें",
    saving: "सहेज रहे…",
    analysisComplete: "उपग्रह विश्लेषण पूर्ण",
    drawFirst: "पहले मानचित्र पर खेत की सीमा बनाएं।",
    loginRequired: "खेत सहेजने के लिए लॉगिन करें।",
    backendDown: "सर्वर तक नहीं पहुँच सके। Python API चालू करें।",
    smsSent: "OTP SMS से भेजा गया +91",
    invalidPhone: "वैध 10-अंकीय नंबर दर्ज करें",
    enterOtp6: "6-अंकों का OTP दर्ज करें",
    resendIn: "पुनः भेजें",
    resendOtp: "OTP पुनः भेजें",
    serverError: "सर्वर त्रुटि। पुनः प्रयास करें।",
    farmDetailsTitle: "खेत विवरण",
    farmDetailsDesc: "आपकी प्रोफ़ाइल में सहेजा जाएगा।",
    cropType: "फसल प्रकार",
    irrigationType: "सिंचाई प्रकार",
    soilType: "मिट्टी प्रकार",
    saveContinue: "सहेजें और आगे बढ़ें",
    listingLive: "सूची सक्रिय",
    listCombined: "संयुक्त क्रेडिट सूचीबद्ध करें",
    verifiedBalance: "आपका सत्यापित शेष",
    creditsToList: "सूचीबद्ध क्रेडिट (tCO2e)",
    pricePerCredit: "प्रति क्रेडिट मूल्य (₹)",
    mintAndList: "मिंट और बाज़ार में सूचीबद्ध",
    processing: "प्रक्रिया…",
    mintSuccess: "टोकन मिंट हुआ",
    chainRequired: "ब्लॉकचेन कनेक्ट नहीं है।",
    otpFailed: "OTP भेजने में विफल",
    areaLabel: "क्षेत्र",
    mapped: "मैप किया",
    credits: "क्रेडिट",
    totalCredits: "कुल क्रेडिट",
    score: "स्कोर",
    canopy: "वन canopy",
    accuracy: "सटीकता",
    liveGps: "लाइव GPS",

    // Layout & Navigation additions
    dashboard: "डैशबोर्ड",
    landVerification: "भूमि सत्यापन",
    carbonPassport: "कार्बन पासपोर्ट",
    creditPooling: "क्रेडिट पूलिंग",
    esgDashboard: "ईएसजी डैशबोर्ड",
    fpoDashboard: "एफपीओ डैशबोर्ड",
    adminDashboard: "व्यवस्थापक डैशबोर्ड",
    adminCompliance: "व्यवस्थापक अनुपालन",
    bulkAutoMatch: "थोक ऑटो-मैच",
    certificates: "प्रमाणपत्र",
    fpoAuditDesk: "एफपीओ ऑडिट डेस्क",
    fpoDesk: "एफपीओ डेस्क",
    walletLedger: "वॉलेट और यूपीआई लेज़र",
    notifications: "सूचनाएं",
    noNotifications: "अभी कोई सूचना नहीं है",
    login: "लॉगिन",

    // Tutorial additions
    skip: "छोड़ें",
    step: "चरण",
    of: "का",
    completed: "पूर्ण",
    tutorialNavHint: "नेविगेट करने के लिए बाएँ/दाएँ तीर कुंजियों या बटनों का उपयोग करें",
    restartTutorial: "ट्यूटोरियल पुनः आरंभ करें",
    nextStep: "अगला चरण",
    proceedToFarm: "मेरे खेत पर जाएँ",

    // Role Selection additions
    backToGateway: "गेटवे पर वापस जाएँ",
    roleAccessPortal: "भूमिका-आधारित एक्सेस पोर्टल",
    selectEcosystemRole: "पारिस्थितिकी तंत्र भूमिका चुनें",
    selectRoleSubtitle: "अनुकूलित डैशबोर्ड, सत्यापन वर्कफ़्लो और बाज़ार पोर्टल तक पहुँचने के लिए अपनी भूमिका चुनें।",
    enterPortal: "पोर्टल में प्रवेश करें",
    farmerLandOwner: "किसान और भूमि स्वामी",
    farmerLandOwnerDesc: "तेलुगु/हिन्दी/अंग्रेजी वॉयस इनपुट के माध्यम से खेत पार्सल पंजीकृत करें, एआई सत्यापन के लिए भूमि दस्तावेज अपलोड करें, और प्रत्यक्ष यूपीआई कार्बन क्रेडिट भुगतान प्राप्त करें।",
    fpoOfficer: "एफपीओ / सहकारी अधिकारी",
    fpoOfficerDesc: "सदस्य किसानों का प्रबंधन करें, बल्क ऑनबोर्डिंग करें, ग्राउंड-ट्रुथ रिकॉर्ड का निरीक्षण करें और सहकारी क्रेडिट पूलिंग निष्पादित करें।",
    corporateBuyer: "कॉर्पोरेट खरीदार और ईएसजी अधिकारी",
    corporateBuyerDesc: "सत्यापित कार्बन क्रेडिट लिस्टिंग ब्राउज़ करें, बल्क ऑटो-मैच आवंटन एल्गोरिदम चलाएं और स्कोप 1-3 सेवानिवृत्ति प्रमाणपत्र प्रबंधित करें।",

    // Voice & Registration additions
    voicePrompt: "नामांकन के लिए कृपया अपना कानूनी पूरा नाम, मोबाइल नंबर और पहचान विवरण दर्ज करें।",
    voiceNotSupported: "इस ब्राउज़र में वॉयस इनपुट समर्थित नहीं है। कृपया अपना विवरण टाइप करें।",
    voiceCaptureError: "आपकी आवाज़ रिकॉर्ड नहीं की जा सकी। कृपया अपना विवरण टाइप करें।",
    voiceDeviceError: "इस डिवाइस पर वॉयस इनपुट शुरू नहीं किया जा सका। कृपया अपना विवरण टाइप करें।",
    phoneOtpVerification: "फ़ोन ओटीपी सत्यापन",
    enter6DigitCode: "6-अंकों का कोड दर्ज करें",
    resendCode: "कोड पुनः भेजें",
    resendingCode: "पुनः भेजा जा रहा है…",
    didntReceiveCode: "कोड प्राप्त नहीं हुआ?",
    cancel: "रद्द करें",
    verifyAndRoute: "सत्यापित करें और आगे बढ़ें",
    codeDispatchedTo: "एक 6-अंकीय प्रमाणीकरण कोड भेजा गया है",

    // Farmland & Dashboard additions
    enrollFirstParcel: "अपना पहला पार्सल नामांकित करें",
    switchFarm: "खेत बदलें:",
    selectedLandParcel: "चयनित भूमि पार्सल:",
    noFarmsEnrolled: "अभी तक कोई खेत नामांकित नहीं है",
    monitoringFlagged: "निगरानी में चिह्नित",
    fpoInspected: "एफपीओ निरीक्षण रिकॉर्ड"
  },
  te: {
    // General / Navigation
    home: "హోమ్",
    farm: "పొలం",
    market: "మార్కెట్",
    wallet: "వాలెట్",
    support: "సహాయం",
    logout: "లాగ్అవుట్",
    phone: "ఫోన్ నంబర్",
    otp: "ఓటీపీ",
    aadhaar: "ఆధార్ నంబర్",
    state: "రాష్ట్రం",
    district: "జిల్లా",
    village: "గ్రామం",
    upiId: "UPI ఐడీ / VPA",
    welcome: "స్వాగతం",
    continue: "కొనసాగించు",
    back: "వెనుకకు",
    submit: "సమర్పించు",
    helpline: "హెల్ప్‌లైన్",
    liveChat: "లైవ్ చాట్ సహాయం",
    verified: "ధృవీకరించబడింది",
    pending: "పెండింగ్‌లో ఉంది",

    // Role Selection
    selectRole: "మీ ప్రొఫైల్ పోర్టల్‌ను ఎంచుకోండి",
    selectRoleDesc: "కార్బన్ఎక్స్ (CarbonX) ప్రీమియం అగ్రిటెక్ పర్యావరణ వ్యవస్థతో పరస్పర చర్య చేయడానికి మీ ఇంటర్‌ఫేస్‌ను ఎంచుకోండి.",
    farmerRole: "భారతీయ రైతు (రైతు సోదరుడు)",
    farmerRoleDesc: "మీ భూమిని నమోదు చేసుకోండి, NDVI ఉపగ్రహ కొలతలను చూడండి మరియు తక్షణ UPI కార్బన్ చెల్లింపులను పొందండి.",
    corporateRole: "కార్పొరేట్ ESG కొనుగోలుదారు",
    corporateRoleDesc: "ధృవీకరించబడిన కార్బన్ క్రెడిట్లను కొనుగోలు చేయండి, BRSR నివేదికలను ఆడిట్ చేయండి మరియు స్థిరమైన వ్యవసాయ-అటవీపెంపకానికి నిధులు సమకూర్చండి.",
    adminRole: "ISRO / ప్రభుత్వ నిర్వాహకుడు",
    adminRoleDesc: "ఉపగ్రహ క్రమరాహిత్య ఫ్లాగ్‌లను ఆడిట్ చేయండి, డ్రోన్ KYC సమర్పణలను సమీక్షించండి మరియు బ్లాక్‌చైన్ కార్బన్ మింటింగ్‌ను పర్యవేక్షించండి.",

    // Login
    loginWelcome: "మళ్లీ స్వాగతం",
    loginDesc: "కార్బన్ నిల్వ స్థితి మరియు మీ సంపాదనను చూడటానికి లాగిన్ చేయండి.",
    registeredPhone: "నమోదిత ఫోన్ నంబర్",
    enterOtp: "4-అంకెల ఓటీపీని నమోదు చేయండి",
    changePhone: "ఫోన్ నంబర్ మార్చండి",
    sendOtp: "ఓటీపీ పంపండి",
    loginBtn: "లాగిన్ చేయండి",
    firstTime: "కార్బన్ఎక్స్‌ను మొదటిసారి ఉపయోగిస్తున్నారా?",
    registerFarmProfile: "కొత్త ఫార్మ్ ప్రొఫైల్‌ను నమోదు చేసుకోండి 🌾",

    // Register
    verifyMobile: "మొబైల్ ధృవీకరణ",
    verifyMobileDesc: "సురక్షితమైన ఓటీపీని స్వీకరించడానికి మీ మొబైల్ నంబర్‌ను నమోదు చేయండి.",
    preferredLang: "ఇష్టపడే భాష",
    farmlandProfile: "వ్యవసాయ భూమి ప్రొఫైల్",
    aadhaarDesc: "కార్బన్ ఆడిట్‌ల కోసం గుర్తింపు ధృవీకరణ మ్యాపింగ్‌ను ఏర్పాటు చేయండి.",
    fullName: "పూర్తి పేరు (ఆధార్ ప్రకారం)",
    aadhaarNumber: "ఆధార్ నంబర్ (UID)",
    verifyAadhaar: "ఆధార్ ధృవీకరించి కొనసాగించండి",
    directBank: "నేరుగా బ్యాంక్ చెల్లింపులు",
    bankDesc: "చెల్లింపుల కొరకు లింక్ చేయబడిన UPI / ఆధార్-ఆధారిత బ్యాంక్ ఖాతాను సెటప్ చేయండి.",
    bankInfo: "తక్షణ కార్బన్ డిపాజిట్ల కోసం ఇది బ్యాంక్ ఖాతా వివరాలతో సరిపోలుతుంది.",
    upiSecured: "గ్లోబల్ కార్బన్ కొనుగోలుదారులు మీ ధృవీకరించబడిన క్రెడిట్లను కొనుగోలు చేసిన వెంటనే UPI చెల్లింపు సెటప్ తక్షణ సెటిల్‌మెంట్‌ను సురక్షితం చేస్తుంది.",
    linkAccount: "ఖాతాను లింక్ చేయండి & KYC పూర్తి చేయండి",
    profileVerified: "ప్రొఫైల్ ధృవీకరించబడింది",
    profileVerifiedDesc: "అభినందనలు రమేష్ కుమార్! మీ ఆధార్ గుర్తింపు మరియు బ్యాంక్ చెల్లింపుల వివరాలు పూర్తిగా ధృవీకరించబడ్డాయి. ఇప్పుడు మీరు మీ పొలం మ్యాప్ చేయడానికి సిద్ధంగా ఉన్నారు.",
    startTutorial: "స్వాగత ట్యుటోరియల్ ప్రారంభించండి",

    // Onboarding/Tutorial
    tutorialTitle: "ఉపగ్రహ నేల ధృవీకరణ",
    tutorialDesc: "నాసా మరియు ఇస్రో యొక్క మల్టీ-స్పెక్ట్రల్ ఉపग्रह చిత్రాలు మీ నేలలోని సేంద్రీయ కార్బన్ సాంద్రతను నేల సేకరించాల్సిన అవసరం లేకుండానే స్కాన్ చేస్తాయి.",
    tutorialTitle2: "UPI వాలెట్ చెల్లింపులు",
    tutorialDesc2: "కార్బన్ క్రెడిట్లు ధృవీకరించబడి మరియు మింట్ చేయబడిన వెంటనే, నిధులు నేరుగా మీ బ్యాంక్ ఖాతాకు UPI ద్వారా పంపబడతాయి.",
    tutorialTitle3: "రియల్ టైమ్ NDVI పర్యవేక్షణ",
    tutorialDesc3: "అధిక-రిజల్యూషన్ వృక్ష ఆరోగ్య చార్ట్‌లు, ఉష్ణోగ్రత సూచికలు మరియు జీవవైవిధ్య హెచ్చరికలను నేరుగా మీ ఫోన్‌లో పొందండి.",
    getStarted: "మ్యాపింగ్ ప్రారంభించండి",

    // Farm Map
    bhuvanGeoportal: "భువన్ జియోపోర్టల్ | 2D వ్యూయర్",
    nasaIsroLive: "NASA/ISRO లైవ్",
    drawTool: "డ్రా టూల్ (రేఖాచిత్రం)",
    measureArea: "వైశాల్యం కొలవండి",
    cadastralBoundary: "కాడస్ట్రల్ (భూమి రిజిస్టర్) సరిహద్దు",
    enterCity: "నగరం లేదా అక్షాంశం, రేఖాంశం నమోదు చేయండి (ఉదా: వరంగల్ లేదా 17.9,79.5)",
    baseLayer: "బేస్ లేయర్",
    satelliteMap: "శాటిలైట్ మ్యాప్",
    ndviIndex: "NDVI (వృక్ష ఆరోగ్య) సూచిక",
    soilMoisture: "నేల తేమ",
    terrainMap: "భూభాగం (Terrain) మ్యాప్",
    calculatedArea: "లెక్కింపబడిన వైశాల్యం",
    nodesPlotted: "గుర్తించిన బిందువులు",
    socDensity: "నేల కార్బన్ సూచిక (SOC)",
    carbonValueEst: "అంచనా వేసిన కార్బన్ విలువ",
    tapToPlot: "మీ పొలం సరిహద్దులను గుర్తించడానికి పైన ఉన్న శాటిలైట్ స్క్రీన్‌పై నొక్కండి!",
    plotMore: "సరిహద్దును ఏర్పరచడానికి కనీసం 3 బిందువులను గుర్తించండి...",
    boundaryClosed: "సరిహద్దు పూర్తయింది! వైశాల్యం: ",
    syncArea: "వైశాల్యం సింక్ చేయి",
    startPlotting: "ప్లాటింగ్ ప్రారంభించండి",
    gpsLocating: "రమేష్ కుమార్ పొలం పై జీपीएस లాక్ చేయబడింది: వెంకటేశ్వర పల్లి, వరంగల్.",

    // Dashboard
    activeFarms: "సక్రియ ధృవీకరించబడిన పొలాలు",
    upiWalletBalance: "UPI వాలెట్ బ్యాలెన్స్",
    carbonSequestration: "కార్బన్ నిల్వ పరిమాణం",
    activeContracts: "సక్రియ స్మార్ట్ ఒప్పందాలు (Contracts)",
    withdrawFunds: "డబ్బు విత్‌డ్రా చేసుకోండి",
    blockchainCert: "బ్లాక్‌చైన్ ERC-1155 ఖాతా పుస్తకం",
    viewCertificate: "ధృవీకరణ పత్రం చూడండి",
    creditsMinted: "మింట్ చేయబడిన క్రెడిట్లు",
    payoutHistory: "చెల్లింపులు మరియు కార్యాచరణ చరిత్ర",
    recentSync: "ఇటీవలే ఉపగ్రహ సింక్ విజయవంతంగా పూర్తయింది.",
    biodiversityIndex: "జీవవైవిధ్య స్కోరు",
    nitrogenLevels: "నేలలో నైట్రోజన్ సాంద్రత",

    // Farm Analytics
    multiSpectral: "మల్టీ-స్పెక్ట్రల్ శాటిలైట్ విశ్లేషణ",
    farmHealthDashboard: "పొలం ఆరోగ్యం & కార్బన్ నిల్వ అంచనా",
    sequestrationTrend: "అంచనా వేసిన కార్బൻ నిల్వ (tCO2e)",
    vegHealthIndex: "వృక్ష ఆరోగ్యం (NDVI) చారిత్రక గ్రాఫ్",
    greenAiRec: "గ్రీన్ AI వ్యవసాయ సూచనలు",
    aiRecText1: "నైట్రోజన్ స్థాయిలు చాలా బాగున్నాయి. 30% నీటిని ఆదా చేయడానికి మరియు హెక్టారుకు అదనంగా 2.5 కార్బన్ క్రెడిట్లను పొందడానికి నేరుగా విత్తే పద్ధతికి మారండి.",
    aiRecText2: "NDVI బలమైన కిరణజన్య సంయోగ క్రియ సాంద్రతను చూపుతోంది. నేలలో తేమను నిలుపుకోవడానికి సేంద్రీయ ఎరువుల పొరలను జోడించడం మంచిది.",
    anomaliesLog: "ఉపగ్రహ క్రమరాహిత్యం & సమ్మతి లాగ్‌లు",
    noAnomalies: "అన్ని ఉపగ్రహ స్కాన్‌లు సక్రమంగా ఉన్నాయి. గత 90 రోజులలో ఎలాంటి క్రమరాహిత్యాలు కనుగొనబడలేదు.",

    dashGreeting: "నమస్తే",
    carbonLabel: "కార్బన్",
    bioLabel: "జీవవైవిధ్యం",
    combinedLabel: "మొత్తం",
    farmsMapped: "పొలాలు మ్యాప్",
    noFarmsYet: "ఇంకా పొలాలు లేవు. GEE మ్యాప్‌లో సరిహద్దు గీసి ఉపగ్రహ విశ్లేషణ చేయండి.",
    mapFarmGee: "పొలం మ్యాప్ (GEE)",
    mapFarmDesc: "ఉపగ్రహ + సరిహద్దు",
    marketplaceTitle: "మార్కెట్",
    marketplaceDesc: "మొత్తం క్రెడిట్లు అమ్మండి",
    listOnChain: "బ్లాక్‌చైన్‌లో జాబితా",
    marketPageTitle: "CarbonX మార్కెట్",
    marketPageSubtitle: "ధృవీకరించబడిన కార్బన్ + జీవవైవిధ్య క్రెడిట్లు",
    searchFarmer: "రైతు లేదా ప్రాంతం వెతకండి…",
    listMyCredits: "నా క్రెడిట్లు జాబితా",
    loadingListings: "జాబితాలు లోడ్…",
    noListings: "ఇంకా జాబితాలు లేవు.",
    buyBid: "కొనుగోలు / బిడ్",
    bidPlaced: "బిడ్ వేయబడింది",
    onChain: "చైన్‌లో",
    chainOffline: "చైన్ ఆఫ్‌లైన్",
    geeMapTitle: "GEE ఉపగ్రహ పొలం మ్యాపింగ్",
    geeMapDesc: "ప్రాంతం వెతకండి, సరిహద్దు గీయండి, Earth Engine విశ్లేషణ చేయండి.",
    scanAi: "AI స్కాన్",
    scanning: "స్కాన్…",
    savePlot: "ప్లాట్ సేవ్",
    saving: "సేవ్…",
    analysisComplete: "ఉపగ్రహ విశ్లేషణ పూర్తి",
    drawFirst: "ముందుగా మ్యాప్‌లో పొలం సరిహద్దు గీయండి.",
    loginRequired: "పొలం సేవ్ చేయడానికి లాగిన్ అవ్వండి.",
    backendDown: "సర్వర్‌కు చేరుకోలేకపోయాం. Python API ప్రారంభించండి.",
    smsSent: "OTP SMS పంపబడింది +91",
    invalidPhone: "10 అంకెల ఫోన్ నంబర్ ఇవ్వండి",
    enterOtp6: "6-అంకెల OTP నమోదు చేయండి",
    resendIn: "మళ్లీ పంపు",
    resendOtp: "OTP మళ్లీ పంపు",
    serverError: "సర్వర్ లోపం. మళ్లీ ప్రయత్నించండి.",
    farmDetailsTitle: "పొలం వివరాలు",
    farmDetailsDesc: "మీ ప్రొఫైల్‌లో సేవ్ అవుతుంది.",
    cropType: "పంట రకం",
    irrigationType: "నీటిపారుదల",
    soilType: "నేల రకం",
    saveContinue: "సేవ్ & కొనసాగు",
    listingLive: "జాబితా లైవ్",
    listCombined: "మొత్తం క్రెడిట్లు జాబితా",
    verifiedBalance: "మీ ధృవీకరించబడిన బ్యాలెన్స్",
    creditsToList: "జాబితా క్రెడిట్లు (tCO2e)",
    pricePerCredit: "క్రెడిట్‌కు ధర (₹)",
    mintAndList: "మింట్ & మార్కెట్‌లో జాబితా",
    processing: "ప్రాసెస్…",
    mintSuccess: "టోకెన్ మింట్",
    chainRequired: "బ్లాక్‌చైన్ కనెక్ట్ కాలేదు.",
    otpFailed: "OTP పంపడం విఫలమైంది",
    areaLabel: "వైశాల్యం",
    mapped: "మ్యాప్",
    credits: "క్రెడిట్లు",
    totalCredits: "మొత్తం క్రెడిట్లు",
    score: "స్కోరు",
    canopy: "canopy",
    accuracy: "ఖచ్చితత్వం",
    liveGps: "లైవ్ GPS",

    // Layout & Navigation additions
    dashboard: "డ్యాష్‌బోర్డ్",
    landVerification: "భూమి ధృవీకరణ",
    carbonPassport: "కార్బన్ పాస్‌పోర్ట్",
    creditPooling: "క్రెడిట్ పూలింగ్",
    esgDashboard: "ESG డ్యాష్‌బోర్డ్",
    fpoDashboard: "FPO డ్యాష్‌బోర్డ్",
    adminDashboard: "అడ్మిన్ డ్యాష్‌బోర్డ్",
    adminCompliance: "అడ్మిన్ సమ్మతి",
    bulkAutoMatch: "బల్క్ ఆటో-మ్యాచ్",
    certificates: "ధృవీకరణ పత్రాలు",
    fpoAuditDesk: "FPO ఆడిట్ డెస్క్",
    fpoDesk: "FPO డెస్క్",
    walletLedger: "వాలెట్ & UPI ఖాతా పుస్తకం",
    notifications: "నోటిఫికేషన్‌లు",
    noNotifications: "ఇంకా నోటిఫికేషన్‌లు లేవు",
    login: "లాగిన్",

    // Tutorial additions
    skip: "దాటవేయి",
    step: "దశ",
    of: "లో",
    completed: "పూర్తయింది",
    tutorialNavHint: "ముందుకు వెళ్ళడానికి కుడి/ఎడమ బాణం లేదా బటన్ క్లిక్ చేయండి",
    restartTutorial: "ట్యుటోరియల్ పునఃప్రారంభించండి",
    nextStep: "తదుపరి దశ",
    proceedToFarm: "నా పొలానికి వెళ్లండి",

    // Role Selection additions
    backToGateway: "గేట్‌వేకి తిరిగి వెళ్లండి",
    roleAccessPortal: "పాత్ర-ఆధారిత యాక్సెస్ పోర్టల్",
    selectEcosystemRole: "పర్యావరణ వ్యవస్థ పాత్రను ఎంచుకోండి",
    selectRoleSubtitle: "అనుకూలీకరించిన డ్యాష్‌బోర్డ్‌లు, ధృవీకరణ ప్రక్రియలు మరియు మార్కెట్‌ప్లేస్ పోర్టల్‌లను యాక్సెస్ చేయడానికి మీ పాత్రను ఎంచుకోండి.",
    enterPortal: "పోర్టల్‌లోకి ప్రవేశించండి",
    farmerLandOwner: "రైతు & భూ యజమాని",
    farmerLandOwnerDesc: "తెలుగు/హిందీ/ఇంగ్లీష్ వాయిస్ ఇన్‌పుట్ ద్వారా వ్యవసాయ ప్లాట్లను నమోదు చేసుకోండి, AI ధృవీకరణ కోసం భూమి పత్రాలను అప్‌లోడ్ చేయండి మరియు ప్రత్యక్ష UPI కార్బన్ క్రెడిట్ చెల్లింపులను పొందండి.",
    fpoOfficer: "FPO / సహకార సంఘం అధికారి",
    fpoOfficerDesc: "సభ్యులైన రైతులను నిర్వహించండి, బల్క్ ఆన్‌బోర్డింగ్ చేయండి, క్షేత్రస్థాయి రికార్డులను తనిఖీ చేయండి మరియు సహకార క్రెడిట్ పూలింగ్‌ను అమలు చేయండి.",
    corporateBuyer: "కార్పొరేట్ కొనుగోలుదారు & ESG అధికారి",
    corporateBuyerDesc: "ధృవీకరించబడిన కార్బన్ క్రెడిట్ జాబితాలను బ్రౌజ్ చేయండి, బల్క్ ఆటో-మ్యాచ్ కేటాయింపు అల్గోరిథంలను అమలు చేయండి మరియు స్కోప్ 1-3 పదవీ విరమణ ధృవీకరణ పత్రాలను నిర్వహించండి.",

    // Voice & Registration additions
    voicePrompt: "నమోదు కొరకు దయచేసి మీ పూర్తి పేరు, మొబైల్ నంబరు మరియు గుర్తింపు వివరాలను నమోదు చేయండి.",
    voiceNotSupported: "ఈ బ్రౌజర్‌లో వాయిస్ ఇన్‌పుట్ మద్దతు లేదు. దయచేసి వివరాలను టైప్ చేయండి.",
    voiceCaptureError: "మీ వాయిస్ రికార్డ్ చేయలేకపోయాము. దయచేసి వివరాలను టైప్ చేయండి.",
    voiceDeviceError: "ఈ పరికరంలో వాయిస్ ఇన్‌పుట్ ప్రారంభించలేకపోయాము. దయచేసి వివరాలను టైప్ చేయండి.",
    phoneOtpVerification: "ఫోన్ ఓటీపీ ధృవీకరణ",
    enter6DigitCode: "6-అంకెల కోడ్‌ను నమోదు చేయండి",
    resendCode: "కోడ్‌ను మళ్లీ పంపండి",
    resendingCode: "మళ్లీ పంపుతోంది…",
    didntReceiveCode: "కోడ్ రాలేదా?",
    cancel: "రద్దు చేయండి",
    verifyAndRoute: "ధృవీకరించి కొనసాగించండి",
    codeDispatchedTo: "6-అంకెల ప్రామాణీకరణ కోడ్ పంపబడింది",

    // Farmland & Dashboard additions
    enrollFirstParcel: "మీ మొదటి ప్లాట్‌ను నమోదు చేసుకోండి",
    switchFarm: "పొలం మార్చండి:",
    selectedLandParcel: "ఎంచుకున్న భూమి ప్లాట్:",
    noFarmsEnrolled: "ఇంకా పొలాలు నమోదు కాలేదు",
    monitoringFlagged: "పర్యవేక్షణలో గుర్తించబడింది",
    fpoInspected: "FPO తనిఖీ చేసిన రికార్డు"
  }
};

const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English', nativeLabel: 'English' },
  { code: 'hi', label: 'Hindi', nativeLabel: 'हिन्दी' },
  { code: 'te', label: 'Telugu', nativeLabel: 'తెలుగు' },
];

function sanitizeLang(lang) {
  if (!lang || typeof lang !== 'string') return 'en';
  const lower = lang.toLowerCase().trim();
  if (lower.startsWith('te') || lower === 'తెలుగు') return 'te';
  if (lower.startsWith('hi') || lower === 'हिन्दी' || lower === 'हिंदी') return 'hi';
  if (lower.startsWith('en')) return 'en';
  return 'en';
}

export function LanguageProvider({ children }) {
  const [currentLang, setCurrentLang] = useState(() => {
    try {
      const stored = localStorage.getItem('carbonx_lang');
      if (stored) return sanitizeLang(stored);
      const userStr = localStorage.getItem('carbonx_user');
      if (userStr) {
        try {
          const userObj = JSON.parse(userStr);
          if (userObj?.preferred_language) {
            return sanitizeLang(userObj.preferred_language);
          }
        } catch { /* ignore */ }
      }
      return 'en';
    } catch {
      return 'en';
    }
  });

  // Listen for storage events (multi-tab sync) and custom language sync events (AuthContext)
  useEffect(() => {
    const handleCustomLang = (e) => {
      const lang = e?.detail?.lang;
      if (lang) {
        const target = sanitizeLang(lang);
        setCurrentLang((prev) => (prev !== target ? target : prev));
      }
    };

    const handleStorage = (e) => {
      if (e.key === 'carbonx_lang' && e.newValue) {
        const target = sanitizeLang(e.newValue);
        setCurrentLang((prev) => (prev !== target ? target : prev));
      }
    };

    window.addEventListener('carbonx:language', handleCustomLang);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener('carbonx:language', handleCustomLang);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const changeLanguage = useCallback((lang) => {
    const target = sanitizeLang(lang);
    setCurrentLang(target);
    try {
      localStorage.setItem('carbonx_lang', target);
      const userStr = localStorage.getItem('carbonx_user');
      if (userStr) {
        try {
          const userObj = JSON.parse(userStr);
          if (userObj && typeof userObj === 'object') {
            userObj.preferred_language = target;
            localStorage.setItem('carbonx_user', JSON.stringify(userObj));
          }
        } catch { /* ignore */ }
      }
    } catch (e) {
      console.warn('Failed to persist language to localStorage:', e);
    }
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('carbonx:language', { detail: { lang: target } }));
    }
  }, []);

  const t = useCallback((key, fallback) => {
    if (!key) return fallback !== undefined ? fallback : '';
    const section = translations[currentLang] || translations.en;
    const val = section?.[key];
    if (val !== undefined && val !== null && val !== '') {
      return val;
    }
    const enVal = translations.en?.[key];
    if (enVal !== undefined && enVal !== null && enVal !== '') {
      return enVal;
    }
    return fallback !== undefined ? fallback : key;
  }, [currentLang]);

  const value = useMemo(() => ({
    currentLang,
    changeLanguage,
    t,
    supportedLanguages: SUPPORTED_LANGUAGES,
    translations,
  }), [currentLang, changeLanguage, t]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    return {
      currentLang: 'en',
      changeLanguage: () => {},
      t: (key, fallback) => {
        const enVal = translations.en?.[key];
        if (enVal !== undefined && enVal !== null && enVal !== '') {
          return enVal;
        }
        return fallback !== undefined ? fallback : key || '';
      },
      supportedLanguages: SUPPORTED_LANGUAGES,
      translations,
    };
  }
  return context;
}

