from backend import ingredients as ing


def flags(text, profile=None, **kw):
    return ing.check(text, profile or {}, kw.get("lang", "en"), eu=False)


# ---- normalizer + aliases ----
def test_normalize_lowercases_and_strips_percent_and_parentheses():
    assert ing.normalize("GLYCERIN 5%") == "glycerin"
    assert ing.normalize("Niacinamide (10%)") == "niacinamide"
    assert ing.normalize("Tocopherol*") == "tocopherol"


def test_aliases():
    assert ing.normalize("Aqua") == "water"
    assert ing.normalize("PARFUM") == "fragrance"
    assert ing.normalize("Parfum (Fragrance)") == "fragrance"
    assert ing.normalize("Cocos Nucifera (Coconut) Oil") == "coconut oil"
    assert ing.normalize("Alcohol Denat.") == "denatured alcohol"


def test_parse_list_keeps_order_and_ignores_commas_in_parentheses():
    assert ing.parse_list("Ingredients: Aqua, Glycerin (vegetable, organic), Parfum.") == ["water", "glycerin", "fragrance"]


def test_parse_list_removes_duplicates_and_may_contain():
    assert ing.parse_list("Aqua, Mica, aqua, Glycerin, may contain: CI 77891") == ["water", "mica", "glycerin"]


# ---- position ----
def test_position_top_middle_end():
    assert ing.position_of(0, 30)["where"] == "top"
    assert ing.position_of(4, 30)["where"] == "top"
    assert ing.position_of(5, 30)["where"] == "middle"
    assert ing.position_of(25, 30)["where"] == "end"
    assert ing.position_of(29, 30)["index"] == 30


def test_alcohol_denat_only_flagged_high_in_the_list():
    high = "Aqua, Alcohol Denat., Glycerin, Mica, Silica, Talc, Zinc Oxide, Citric Acid"
    low = "Aqua, Glycerin, Mica, Silica, Talc, Zinc Oxide, Citric Acid, Alcohol Denat."
    assert any(f["ingredient"] == "denatured alcohol" for f in flags(high)["flags"])
    assert not any(f["ingredient"] == "denatured alcohol" for f in flags(low)["flags"])


def test_explanation_mentions_position():
    f = next(f for f in flags("Aqua, Retinol")["flags"] if f["ingredient"] == "retinol")
    assert f["position"]["index"] == 2 and "top of the list" in f["explanation"]


# ---- avoid list ----
def test_avoid_list_is_red_and_first():
    r = flags("Aqua, Lanolin, Retinol", {"avoid": ["lanolin"]})
    assert r["flags"][0]["ingredient"] == "lanolin" and r["flags"][0]["severity"] == "red"
    assert r["verdict_for_me"]["level"] == "red"


def test_avoid_fragrance_also_catches_parfum_and_allergens():
    r = flags("Aqua, Parfum, Linalool", {"avoid": ["fragrance"]})
    assert {f["ingredient"] for f in r["flags"] if f["severity"] == "red"} == {"fragrance", "linalool"}


def test_nothing_red_without_an_avoid_list():
    assert not [f for f in flags("Aqua, Parfum, Retinol")["flags"] if f["severity"] == "red"]


# ---- personalization ----
def test_pore_clogging_only_for_acne_prone_skin():
    text = "Aqua, Isopropyl Myristate, Glycerin"
    assert any(f["category"] == "pore_clogging_suspects" for f in flags(text, {"skin_type": "oily"})["flags"])
    assert any(f["category"] == "pore_clogging_suspects" for f in flags(text, {"concerns": ["acne"]})["flags"])
    assert not any(f["category"] == "pore_clogging_suspects" for f in flags(text, {"skin_type": "dry"})["flags"])


def test_pore_clogging_note_is_honest_about_the_evidence():
    f = next(f for f in flags("Cocos Nucifera Oil", {"skin_type": "oily"})["flags"] if f["category"] == "pore_clogging_suspects")
    assert "rabbit" in f["explanation"] and "unreliable" in f["explanation"]


def test_fragrance_matters_more_for_sensitive_skin():
    assert next(f for f in flags("Aqua, Parfum")["flags"])["severity"] == "info"
    assert next(f for f in flags("Aqua, Parfum", {"sensitive": True})["flags"])["severity"] == "amber"


def test_green_when_nothing_matters():
    r = flags("Aqua, Glycerin, Tocopherol", {"skin_type": "dry"})
    assert r["verdict_for_me"]["level"] == "green"


# ---- actives ----
def test_retinoid_and_acid_conflict():
    r = flags("Aqua, Retinol, Glycolic Acid")
    assert any("same night" in f["explanation"] for f in r["flags"])


def test_retinol_mentions_pregnancy_and_sun():
    f = next(f for f in flags("Retinol")["flags"] if f["ingredient"] == "retinol")
    assert "doctor" in f["explanation"] and "sun" in f["explanation"]


def test_french_explanations():
    r = ing.check("Aqua, Retinol, Parfum", {"sensitive": True}, "fr", eu=False)
    assert "rétinoïde" in " ".join(f["explanation"] for f in r["flags"]).lower()
    assert "peau sensible" in r["verdict_for_me"]["summary"]


# ---- EU annex matching: a wrong match would call safe ingredients banned ----
def test_eu_match_needs_the_exact_substance():
    dye = {"annex": "II", "display_name": "3(or5)-[[4-[(7-amino-1-hydroxy-3-sulphonato-2-naphthyl)azo]-1-naphthyl]azo]salicylic acid and its salts"}
    assert not ing._same_substance("salicylic acid", dye)


def test_eu_match_finds_names_in_parentheses():
    entry = {"annex": "II", "display_name": "1,4-Dihydroxybenzene (Hydroquinone), with the exception of entry 14 in Annex III"}
    assert ing._same_substance("hydroquinone", entry)


# ---- messy real-world lists ----
def test_full_stop_separated_names_are_split():
    assert ing.parse_list("Aqua, Alcohol Denat. Myristyl Myristate, Glycerin") == ["water", "denatured alcohol", "myristyl myristate", "glycerin"]


def test_junk_after_the_last_ingredient_is_dropped():
    names = ing.parse_list("Aqua, Parfum dope 12m t-no. 89057 890576 cap on recycle 75 mle beiersdorf ag")
    assert names[:2] == ["water", "fragrance"] and not any("beiersdorf" in n for n in names)


def test_one_line_per_ingredient():
    r = flags("Aqua, Parfum", {"avoid": ["fragrance"], "sensitive": True})
    assert [f["ingredient"] for f in r["flags"]].count("fragrance") == 1
    f = r["flags"][0]
    assert f["severity"] == "red" and f["also"] == ["fragrance_and_allergens"] and "common trigger" in f["explanation"]


def test_french_names_and_grammar():
    r = ing.check("Aqua, Parfum, Retinol, Glycolic Acid", {"avoid": ["fragrance"]}, "fr", eu=False)
    assert r["flags"][0]["ingredient"] == "parfum"
    assert "parfum, qui est sur ta liste" in r["verdict_for_me"]["summary"]
    assert any(f["ingredient"] == "rétinoïdes + AHA" for f in r["flags"])


def test_plural_avoid_summary():
    assert "which are on your avoid list" in flags("Parfum, Linalool", {"avoid": ["fragrance"]})["verdict_for_me"]["summary"]
