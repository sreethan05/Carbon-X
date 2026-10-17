"""Multilingual prompt templates and localized formatters for CarbonX Farmer Voice Assistant.

Supports Telugu (te-IN), Hindi (hi-IN), and English (en-IN).
Provides safe conversational guidance, tool definitions, and natural language
query resolution formatters for smallholder farmers.
"""
from typing import Any, Optional

SYSTEM_PROMPT = (
    "You are the CarbonX Farmer Assistant. Help only the authenticated user with their own account. "
    "Support Telugu, Hindi, English, and mixed speech. Use backend tools for account data. Never invent "
    "values or reveal another user's data, PII, documents, phone, Aadhaar, bank, UPI, tokens, passwords, "
    "or internal IDs. Phone OTP confirms phone control only; it is not Aadhaar eKYC. Never approve land, "
    "issue credits, approve payments, change payout details, or change benefit-sharing. Ask confirmation "
    "before saving form values. Use only authorized tools and backend results."
)

TELUGU_INSTRUCTIONS = (
    "మీరు CarbonX రైతు సహాయకులు (Farmer Assistant). రైతులకు వారి స్వంత ఖాతా వివరాలు, "
    "పొలాలు, కార్బన్ మరియు జీవవైవిధ్య స్కోరు, క్రెడిట్లు, ఆదాయం మరియు భూమి నమోదు విధానం గురించి "
    "సరళమైన, మర్యాదపూర్వకమైన తెలుగులో సమాధానం ఇవ్వండి. ఎలాంటి వ్యక్తిగత లేదా రహస్య వివరాలు "
    "(ఆధార్, బ్యాంక్, UPI, OTP) అడగవద్దు లేదా వెల్లడించవద్దు."
)

HINDI_INSTRUCTIONS = (
    "आप CarbonX किसान सहायक हैं. किसानों को केवल उनके अपने खाते की जानकारी, "
    "खेत, कार्बन और जैव विविधता स्कोर, क्रेडिट, कमाई और भूमि ऑनबोर्डिंग प्रक्रिया के बारे में "
    "सरल और स्पष्ट हिंदी में सहायता प्रदान करें. किसी भी प्रकार की संवेदनशील जानकारी "
    "(आधार, बैंक, यूपीआई, ओटीपी) न पूछें और न ही साझा करें."
)

ENGLISH_INSTRUCTIONS = (
    "You are the CarbonX Farmer Assistant. Provide clear, concise, and respectful assistance "
    "to smallholder farmers regarding their plots, satellite carbon and biodiversity scores, "
    "credit balance, earnings, and land onboarding. Protect privacy and enforce consent."
)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return JSON schema definitions for all authorized voice tools."""
    def fn(name: str, description: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties or {},
                    "additionalProperties": False,
                },
            },
        }

    return [
        fn("get_my_plots", "Return the authenticated farmer's plot summary only."),
        fn("get_my_document_status", "Return the authenticated farmer's land document verification status."),
        fn("get_my_score", "Return the authenticated farmer's carbon and biodiversity score summary."),
        fn("get_my_credits", "Return the authenticated farmer's credit totals."),
        fn("get_my_earnings", "Return the authenticated farmer's earning summary."),
        fn("get_my_payout_status", "Return payout status without bank, UPI, or beneficiary details."),
        fn("search_location", "Search a village or location in India.", {"query": {"type": "string", "maxLength": 120}}),
        fn("explain_land_onboarding", "Explain CarbonX land onboarding steps."),
        fn("navigate_to", "Navigate to a safe CarbonX page.", {"target": {"type": "string", "maxLength": 40}}),
        fn(
            "propose_safe_form_update",
            "Propose safe form values that require farmer confirmation before saving.",
            {"fields": {"type": "object", "additionalProperties": {"type": "string", "maxLength": 120}}},
        ),
    ]


def format_tool_response(tool_name: str, tool_result: dict[str, Any], language_code: str, user_text: str = "") -> str:
    """Format tool execution results into helpful, natural multilingual responses."""
    lang = language_code or "te-IN"

    if tool_name == "get_my_plots":
        count = tool_result.get("count", 0)
        plots = tool_result.get("plots", [])
        total_ha = sum(float(p.get("area_hectares") or 0) for p in plots)
        if count == 0:
            if lang == "hi-IN":
                return "आपके खाते में अभी कोई खेत पंजीकृत नहीं है. नया खेत जोड़ने के लिए ऑनबोर्डिंग शुरू करें."
            if lang == "te-IN":
                return "మీ ఖాతాలో ప్రస్తుతం పొలాలు ఏవీ నమోదు కాలేదు. కొత్త పొలాన్ని నమోదు చేయడానికి ప్రారంభించండి."
            return "You have no registered plots yet. You can start onboarding to register a new plot."
        if lang == "hi-IN":
            return f"आपके खाते में कुल {count} खेत पंजीकृत हैं, जिनका कुल क्षेत्रफल लगभग {total_ha:.1f} हेक्टेयर है."
        if lang == "te-IN":
            return f"మీ ఖాతాలో మొత్తం {count} పొలాలు నమోదై ఉన్నాయి. మొత్తం వైశాల్యం సుమారు {total_ha:.1f} హెక్టార్లు."
        return f"You have {count} registered plot(s) with an approximate total area of {total_ha:.1f} hectares."

    if tool_name == "get_my_score":
        scores = tool_result.get("scores", {})
        carbon = scores.get("carbon_tonnes", 0.0)
        credits = scores.get("total_credits", 0.0)
        bio = scores.get("biodiversity_score", 0.0)
        plots_count = tool_result.get("plots_count", 0)
        if lang == "hi-IN":
            return (
                f"आपके {plots_count} खेत(खेतों) का स्कोर: कुल कार्बन क्रेडिट: {credits}, "
                f"कार्बन संचयन: {carbon} टन, और जैव विविधता स्कोर: {bio}/100."
            )
        if lang == "te-IN":
            return (
                f"మీ {plots_count} పొలాల స్కోరు: మొత్తం కార్బన్ క్రెడిట్లు: {credits}, "
                f"కార్బన్ నిల్వ: {carbon} టన్నులు, మరియు జీవవైవిధ్య స్కోరు: {bio}/100."
            )
        return (
            f"Your score for {plots_count} plot(s): total credits: {credits}, "
            f"carbon: {carbon} tonnes, biodiversity score: {bio}/100."
        )

    if tool_name == "get_my_credits":
        credits = tool_result.get("credits", {})
        total = credits.get("total_credits", 0.0)
        active = tool_result.get("active_listings", 0)
        if lang == "hi-IN":
            return f"आपके खाते में कुल {total} क्रेडिट उपलब्ध हैं, जिनमें {active} सक्रिय लिस्टिंग हैं."
        if lang == "te-IN":
            return f"మీ ఖాతాలో మొత్తం {total} క్రెడిట్లు అందుబాటులో ఉన్నాయి ({active} క్రియాశీల లిస్టింగ్‌లు)."
        return f"You have {total} total credits available with {active} active listing(s)."

    if tool_name == "get_my_earnings":
        earnings = tool_result.get("estimated_earnings", 0.0)
        currency = tool_result.get("currency", "INR")
        if lang == "hi-IN":
            return f"आपकी वर्तमान अनुमानित कमाई ₹{earnings:,.2f} {currency} है."
        if lang == "te-IN":
            return f"మీ ప్రస్తుత అంచనా ఆదాయం ₹{earnings:,.2f} {currency}."
        return f"Your estimated earnings are ₹{earnings:,.2f} {currency}."

    if tool_name == "get_my_document_status":
        status = tool_result.get("status", "PENDING")
        reasons = tool_result.get("reasons", [])
        reasons_text = f" ({', '.join(str(r) for r in reasons)})" if reasons else ""
        if lang == "hi-IN":
            status_hi = {"VERIFIED": "सत्यापित", "PENDING": "लंबित", "FLAGGED": "समीक्षाधीन"}.get(status, status)
            return f"आपके भूमि दस्तावेजों की स्थिति: {status_hi}{reasons_text}."
        if lang == "te-IN":
            status_te = {"VERIFIED": "ధ్రువీకరించబడింది", "PENDING": "పరిశీలనలో ఉంది", "FLAGGED": "సమీక్ష అవసరం"}.get(status, status)
            return f"మీ భూమి పత్రాల ధ్రువీకరణ స్థితి: {status_te}{reasons_text}."
        return f"Your land document verification status is {status}{reasons_text}."

    if tool_name == "explain_land_onboarding":
        if lang == "hi-IN":
            return (
                "CarbonX भूमि ऑनबोर्डिंग के 5 आसान चरण हैं: "
                "1. भूमि दस्तावेज (पट्टा) सत्यापित करें, "
                "2. मानचित्र पर खेत की सीमा बनाएं, "
                "3. सैटेलाइट कार्बन और जैव विविधता स्कोर देखें, "
                "4. खेत सुरक्षित करें, "
                "5. पात्र होने पर स्वीकृत क्रेडिट मार्केटप्लेस पर बेचें."
            )
        if lang == "te-IN":
            return (
                "CarbonX భూమి నమోదు 5 సులభ దశలు: "
                "1. పట్టా లేదా భూమి పత్రాల ధ్రువీకరణ, "
                "2. మ్యాప్‌పై పొలం సరిహద్దు గీయడం, "
                "3. శాటిలైట్ కార్బన్ మరియు బయోడైవర్సిటీ స్కోర్ పరిశీలన, "
                "4. పొలం వివరాలు భద్రపరచడం, "
                "5. అర్హత ఉన్నప్పుడు క్రెడిట్లు మార్కెట్‌ప్లేస్‌లో అమ్మడం."
            )
        return (
            "CarbonX land onboarding involves 5 steps: "
            "1. Verify land ownership documents, "
            "2. Draw farm boundary on map, "
            "3. Review satellite carbon and biodiversity scores, "
            "4. Save farm plot, "
            "5. List verified credits on the marketplace."
        )

    if tool_name == "get_my_payout_status":
        if lang == "hi-IN":
            return "क्रेडिट बिक्री के बाद भुगतान सीधे आपके पंजीकृत खाते में स्थानांतरित किया जाता है. विवरण वॉलेट में उपलब्ध हैं."
        if lang == "te-IN":
            return "క్రెడిట్ అమ్మకం జరిగిన తర్వాత చెల్లింపు నేరుగా మీ నమోదిత ఖాతాకు జమ అవుతుంది. వివరాలు మీ వాలెట్‌లో చూడవచ్చు."
        return "Payouts are transferred after approved credit sales. Details are available in your wallet."

    if tool_name == "search_location":
        query = tool_result.get("query", "")
        result = tool_result.get("result")
        if result:
            if lang == "hi-IN":
                return f"स्थान '{query}' खोजा गया. मानचित्र पर सीमा रेखांकित करने के लिए तैयार है."
            if lang == "te-IN":
                return f"లొకేషన్ '{query}' కోసం శోధన విజయవంతమైంది. మ్యాప్‌లో సరిహద్దు చూడవచ్చు."
            return f"Location '{query}' found. Ready to view or mark boundary on the map."
        if lang == "hi-IN":
            return f"स्थान '{query}' के लिए कोई स्पष्ट परिणाम नहीं मिला. कृपया जिला या मंडल सहित दोबारा प्रयास करें."
        if lang == "te-IN":
            return f"లొకేషన్ '{query}' కనుగొనబడలేదు. దయచేసి జిల్లా లేదా మండలం పేరుతో మళ్లీ ప్రయత్నించండి."
        return f"Could not find location '{query}'. Please try with mandal or district name."

    if tool_name == "navigate_to":
        target = tool_result.get("target") or ""
        if target == "marketplace":
            if lang == "hi-IN":
                return "मार्केटप्लेस पर ले जाया जा रहा है. वर्तमान में कार्बन क्रेडिट का बाजार भाव ₹400 से ₹1,200 प्रति क्रेडिट है."
            if lang == "te-IN":
                return "మార్కెట్‌ప్లేస్‌కు నావిగేట్ చేస్తున్నాము. ధ్రువీకరించబడిన కార్బన్ క్రెడిట్ల ప్రస్తుత మార్కెట్ ధర సుమారు ₹400 నుండి ₹1,200 వరకు ఉంది."
            return "Navigating to the marketplace. Verified carbon credits currently trade between ₹400 and ₹1,200 per credit."
        if target == "support":
            if lang == "hi-IN":
                return "सहायता और सपोर्ट केंद्र पर ले जाया जा रहा है. आप मुझसे खेत की स्थिति, स्कोर, क्रेडिट, कमाई या ऑनबोर्डिंग के बारे में पूछ सकते हैं."
            if lang == "te-IN":
                return "సహాయం మరియు సపోర్ట్ కేంద్రానికి నావిగేట్ చేస్తున్నాము. మీరు నన్ను పొలం స్థితి, స్కోరు, క్రెడిట్లు, ఆదాయం లేదా రిజిస్ట్రేషన్ గురించి అడగవచ్చు."
            return "Navigating to the support center. You can ask me about your farm status, scores, credits, balance, or onboarding."
        if lang == "hi-IN":
            return "आपके अनुरोध के अनुसार संबंधित पृष्ठ पर ले जाया जा रहा है."
        if lang == "te-IN":
            return "మీ అభ్యర్థన మేరకు సంబంధిత పేజీకి నావిగేట్ చేస్తున్నాము."
        return "Navigating to the requested section."

    if tool_name == "propose_safe_form_update":
        fields = tool_result.get("proposed_fields", {})
        if fields:
            summary = ", ".join(f"{k}: {v}" for k, v in fields.items())
            if lang == "hi-IN":
                return f"फॉर्म विवरण तैयार किए गए हैं: {summary}. सहेजने के लिए कृपया पुष्टि करें."
            if lang == "te-IN":
                return f"ఫారమ్ వివరాలు సిద్ధం చేయబడ్డాయి: {summary}. సేవ్ చేయడానికి దయచేసి ధ్రువీకరించండి."
            return f"Proposed form values: {summary}. Please confirm to save."

    return get_generic_fallback(lang)


def get_generic_fallback(language_code: str) -> str:
    """Return safe privacy-preserving generic fallback response."""
    if language_code == "hi-IN":
        return "मैंने आपके CarbonX खाते से सुरक्षित जानकारी देखी है. कोई निजी जानकारी साझा नहीं की गई."
    if language_code == "te-IN":
        return "మీ CarbonX ఖాతాలోని సురక్షిత వివరాలు చూశాను. వ్యక్తిగత సమాచారం చూపించలేదు."
    return "I checked your CarbonX account safely. No private details were shared."


def get_unclear_audio_fallback(language_code: str) -> str:
    """Return fallback message when voice audio is unclear or empty."""
    if language_code == "hi-IN":
        return "मुझे आपकी आवाज़ स्पष्ट सुनाई नहीं दी. कृपया पुनः प्रयास करें."
    if language_code == "te-IN":
        return "మీ మాట స్పష్టంగా వినిపించలేదు. దయచేసి మళ్లీ మాట్లాడండి."
    return "I could not hear that clearly. Please try again."
