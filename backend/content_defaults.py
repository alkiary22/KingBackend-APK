"""Default editable text content for the app.
Admin can override any value via /api/admin/content. Frontend merges defaults + overrides.
"""

DEFAULT_CONTENT = {
    # Brand
    "brand_name_prefix": "ملك",
    "brand_name_suffix": "التوقعات",

    # Landing
    "landing_badge": "كأس العالم 2026",
    "landing_hero_line1": "توقّع.",
    "landing_hero_line2_strong": "احصد النقاط",
    "landing_hero_line2_rest": ".",
    "landing_hero_line3_prefix": "كن",
    "landing_hero_line3_italic": "ملك التوقعات",
    "landing_hero_line3_suffix": ".",
    "landing_hero_desc": "منصة المسابقات الأقوى لتوقع نتائج مباريات كأس العالم. كل يوم مباريات جديدة، كل توقع صحيح يقربك من العرش.",
    "landing_cta_register": "انضم للمنافسة",
    "landing_cta_login": "لدي حساب",
    "landing_cta_authenticated": "ابدأ التوقع الآن",

    # Feature cards
    "feature_1_title": "نظام نقاط واضح",
    "feature_1_desc": "3 نقاط لتوقع النتيجة الصحيحة، نقطة واحدة للتوقع القريب، و0 نقطة للتوقع الخاطئ.",
    "feature_2_title": "لوحة متصدرين حية",
    "feature_2_desc": "نافس آلاف اللاعبين على لقب ملك التوقعات، وتابع ترتيبك في الوقت الحقيقي.",
    "feature_3_title": "جميع المنتخبات",
    "feature_3_desc": "48 منتخباً من كافة قارات العالم، مع تغطية كاملة لكل مباراة ومرحلة.",

    # Scoring section
    "scoring_pretitle": "آلية الاحتساب",
    "scoring_title": "كيف تربح النقاط؟",
    "scoring_3_title": "توقع النتيجة الصحيحة",
    "scoring_3_desc": "مثال: توقعت 2-1 وكانت النتيجة 2-1",
    "scoring_1_title": "توقع قريب",
    "scoring_1_desc": "توقعت الفريق الفائز بشكل صحيح بنتيجة مختلفة",
    "scoring_0_title": "توقع خاطئ",
    "scoring_0_desc": "لا داعي للحزن، المباراة القادمة فرصتك",

    # Pages
    "matches_pretitle": "جدول المباريات",
    "matches_title": "توقعاتك اليومية",
    "matches_desc": "أدخل توقعاتك لكل مباراة قبل صافرة البداية. كل توقع يحتسب نقاطك تلقائياً.",
    "teams_pretitle": "المنتخبات المشاركة",
    "teams_title": "منتخبات كأس العالم 2026",
    "teams_desc_template": "48 منتخباً من جميع قارات العالم يتنافسون على اللقب الأغلى.",
    "leaderboard_pretitle": "قاعة الملوك",
    "leaderboard_title": "لوحة المتصدرين",
    "leaderboard_desc": "أفضل اللاعبين على مستوى مسابقة ملك التوقعات",

    # Footer
    "footer_text": "ملك التوقعات © 2026 — صُمم لعشاق كرة القدم",
}
