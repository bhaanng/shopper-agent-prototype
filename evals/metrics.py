"""
Eval metric and proxy definitions for the NTO Shopper Agent.

Each proxy has:
  - name:       snake_case identifier (self-explanatory)
  - type:       "positive" | "negative"
  - definition: instruction to the LLM judge

METRIC_SCALES:
  binary  → Yes/No/NA verdict, scores 0.0 or 1.0
  likert  → 1-5 quality score; judge gives improvement comment for < 5
             normalised: (score - 1) / 4  →  [0.0, 1.0]
  ndcg    → NDCG@3 computed from product relevance scoring
"""

METRICS: dict[str, list[dict]] = {

    # ── Likert metrics (subjective quality) ─────────────────────────────────

    "cognitive_load": [
        {
            "name": "follow_up_offers_specific_choices",
            "type": "positive",
            "definition": (
                "After presenting search results, the agent's follow-up question offers "
                "a small, specific set of options (e.g., 2–4 choices) rather than asking "
                "something open-ended, so the user can respond with a short phrase."
            ),
        },
        {
            "name": "search_intent_transparency",
            "type": "positive",
            "definition": (
                "The agent briefly explains why the returned results match the user's "
                "query — e.g., calling out the key attribute it filtered on "
                "(waterproofing, weight, terrain type) — before or alongside the product list."
            ),
        },
        {
            "name": "scannable_result_framing",
            "type": "positive",
            "definition": (
                "Products are presented in a structured, easy-to-scan format: "
                "2–3 highlighted options each with one clear differentiating attribute, "
                "rather than an undifferentiated wall of names or specs."
            ),
        },
        {
            "name": "stacks_multiple_open_ended_questions",
            "type": "negative",
            "definition": (
                "After presenting results, the agent asks multiple open-ended questions "
                "in a dense paragraph without providing options, forcing the user to "
                "compose a complex reply."
            ),
        },
        {
            "name": "dumps_undifferentiated_product_list",
            "type": "negative",
            "definition": (
                "The agent returns a large undifferentiated list of products that the "
                "user must read and evaluate on their own, with no prioritisation, "
                "grouping, or guidance on which to consider first."
            ),
        },
        {
            "name": "shows_results_mismatching_query_without_explanation",
            "type": "negative",
            "definition": (
                "The agent presents products that appear to differ from what the user "
                "asked for (different category, activity type, or key attribute) without "
                "explaining why — leaving the user confused about the mismatch."
            ),
        },
    ],

    "information_gain": [
        {
            "name": "asks_foundational_attributes_before_secondary",
            "type": "positive",
            "definition": (
                "The agent asks for foundational attributes (activity type, terrain, "
                "duration) before aesthetic or secondary details."
            ),
        },
        {
            "name": "questions_follow_logical_funnel_order",
            "type": "positive",
            "definition": (
                "The agent asks questions in a logical order that builds a funnel "
                "(e.g., Activity → Conditions → Budget → Preferences)."
            ),
        },
        {
            "name": "asks_most_critical_category_attribute_first",
            "type": "positive",
            "definition": (
                "The agent immediately identifies the product category and asks for "
                "the most critical attribute specific to that category before anything "
                "else (e.g., asking 'How long are your hikes?' when the user asks for "
                "hiking boots)."
            ),
        },
        {
            "name": "targets_highest_value_situational_question",
            "type": "positive",
            "definition": (
                "The agent leverages the user's specific scenario to ask the "
                "highest-value situational question (e.g., if the user mentions a "
                "rainy Pacific Northwest trip, the agent immediately asks about "
                "waterproofing needs)."
            ),
        },
        {
            "name": "asks_specific_details_before_establishing_basics",
            "type": "negative",
            "definition": (
                "The agent asks for hyper-specific details (e.g., exact boot size, "
                "preferred colour) before establishing the baseline item or activity."
            ),
        },
        {
            "name": "asks_aesthetic_attribute_before_functional_need",
            "type": "negative",
            "definition": (
                "The agent asks about a secondary or aesthetic attribute "
                "(e.g., colour, brand logo style) before establishing the core "
                "functional requirement of the product category."
            ),
        },
        {
            "name": "asks_generic_question_ignoring_product_context",
            "type": "negative",
            "definition": (
                "The agent asks a generic, unprioritised filtering question that "
                "ignores the specific context of the category being discussed "
                "(e.g., asking 'What is your favourite brand?' before establishing "
                "what the product needs to do)."
            ),
        },
    ],

    "refinement_quality": [
        {
            "name": "highlights_key_difference_to_guide_choice",
            "type": "positive",
            "definition": (
                "The agent explicitly highlights the primary difference between two "
                "or more presented options and asks the user to choose based on that "
                "specific difference (e.g., 'Both are waterproof, but the Merrell is "
                "a stiffer boot for rocky terrain while the Salomon is more flexible "
                "for fast hiking. Which style fits your plans?')."
            ),
        },
        {
            "name": "asks_narrow_feature_question_to_gauge_fit",
            "type": "positive",
            "definition": (
                "The agent asks a specific, narrow question about a feature of a "
                "presented product to gauge fit, rather than a general question "
                "(e.g., 'This jacket has a fixed hood — is that okay for you or "
                "would you prefer a removable one?')."
            ),
        },
        {
            "name": "proposes_alternative_when_zero_results",
            "type": "positive",
            "definition": (
                "When a user's constraints result in zero catalog matches, the agent "
                "explicitly explains the conflict and proactively proposes the closest "
                "available alternative by relaxing one constraint, rather than just "
                "saying 'I couldn't find anything'."
            ),
        },
        {
            "name": "ends_turn_with_no_next_step_after_results",
            "type": "negative",
            "definition": (
                "The agent displays products and ends its turn without asking any "
                "guiding question, forcing the user to figure out the next step."
            ),
        },
        {
            "name": "asks_vague_unfocused_question_after_results",
            "type": "negative",
            "definition": (
                "The agent asks a weak, low-effort question after presenting products "
                "that forces the user to do the analytical work "
                "(e.g., 'What do you think of these?' or 'Do any of these look good?')."
            ),
        },
        {
            "name": "lists_overwhelming_specs_without_framing_choice",
            "type": "negative",
            "definition": (
                "The agent lists an overwhelming number of specs or features for "
                "refined options without framing a clear, single-variable choice "
                "for the user to make."
            ),
        },
        {
            "name": "pushes_to_purchase_before_validating_fit",
            "type": "negative",
            "definition": (
                "The agent tries to immediately close the sale after presenting the "
                "very first round of results without checking if the products actually "
                "meet the user's nuanced expectations."
            ),
        },
        {
            "name": "pivots_to_unrelated_category_mid_refinement",
            "type": "negative",
            "definition": (
                "The agent presents products for the current goal but instead of "
                "refining that choice, immediately asks about a completely different "
                "product category."
            ),
        },
    ],

    "tone_persona": [
        {
            "name": "uses_outdoor_brand_vocabulary_naturally",
            "type": "positive",
            "definition": (
                "The agent naturally uses vocabulary appropriate to the brand's domain "
                "(e.g. trail/adventure/gear for outdoor retailers, skincare/routine/formulation "
                "for beauty brands) without sounding forced."
            ),
        },
        {
            "name": "uses_robotic_ai_boilerplate",
            "type": "negative",
            "definition": (
                "The agent uses classic robotic boilerplate "
                "(e.g., 'As an AI language model...', 'I don't have personal "
                "experiences...')."
            ),
        },
        {
            "name": "gives_unsolicited_lengthy_explanation",
            "type": "negative",
            "definition": (
                "The agent provides massive paragraphs of unsolicited advice when "
                "the user asked a simple question."
            ),
        },
        {
            "name": "responds_to_frustration_with_toxic_positivity_or_slang",
            "type": "negative",
            "definition": (
                "The agent responds to user frustration with toxic positivity "
                "or extreme slang."
            ),
        },
        {
            "name": "buries_product_info_with_apologies_and_filler",
            "type": "negative",
            "definition": (
                "The agent repeatedly apologises for minor friction or uses "
                "excessively enthusiastic sycophantic boilerplate that buries "
                "the actual product information."
            ),
        },
    ],

    "rationale_quality": [
        {
            "name": "acknowledges_user_intent_before_results",
            "type": "positive",
            "definition": (
                "Before or while presenting results, the agent explicitly echoes the "
                "user's goal or use-case in its own words, demonstrating it understood "
                "what the user is trying to accomplish."
            ),
        },
        {
            "name": "connects_each_product_feature_to_user_need",
            "type": "positive",
            "definition": (
                "Each recommended product gets a short, relevant callout that connects "
                "one key feature to the user's stated need — not a raw spec dump."
            ),
        },
        {
            "name": "covers_product_space_and_explains_differences",
            "type": "positive",
            "definition": (
                "The agent presents options that meaningfully cover the relevant product "
                "space and explicitly notes the key difference between them so the user "
                "understands why both are shown."
            ),
        },
        {
            "name": "introduces_results_with_no_context_or_rationale",
            "type": "negative",
            "definition": (
                "The agent introduces results with a vague, context-free opener "
                "(e.g., 'Here are some great options!', 'I found these for you!') "
                "that makes no connection to the user's specific goal or constraints."
            ),
        },
    ],

    # ── Binary metrics (objective pass/fail) ────────────────────────────────

    "goal_identification": [
        {
            "name": "translates_vague_symptom_to_product_goal",
            "type": "positive",
            "definition": (
                "The agent successfully translates a vague user problem or symptom "
                "(e.g., 'my feet hurt on long hikes') into a concrete, actionable "
                "product goal before recommending items."
            ),
        },
        {
            "name": "shows_products_before_establishing_use_case",
            "type": "negative",
            "definition": (
                "The agent starts showing products before establishing the baseline "
                "activity, category, or use-case."
            ),
        },
        {
            "name": "ignores_explicitly_stated_primary_goal",
            "type": "negative",
            "definition": (
                "The agent ignores a core goal explicitly stated in the user's "
                "initial prompt."
            ),
        },
        {
            "name": "misidentifies_user_purchase_funnel_stage",
            "type": "negative",
            "definition": (
                "The agent misinterprets the user's position in the purchasing funnel, "
                "e.g., treating a top-of-funnel question ('What's the difference between "
                "trail runners and hiking boots?') as a bottom-of-funnel transaction "
                "('Let me add these boots to your cart!')."
            ),
        },
    ],

    "redundancy_avoidance": [
        {
            "name": "acknowledges_prior_constraints_in_next_question",
            "type": "positive",
            "definition": (
                "The agent actively acknowledges previously gathered constraints "
                "when asking the next question, showing it retained context across turns."
            ),
        },
        {
            "name": "applies_earlier_constraint_without_being_reminded",
            "type": "positive",
            "definition": (
                "The agent explicitly applies a constraint provided earlier in the "
                "conversation without needing to be reminded "
                "(e.g., 'Since you mentioned wet conditions, I filtered to waterproof only')."
            ),
        },
        {
            "name": "combines_facts_from_multiple_turns_into_deduction",
            "type": "positive",
            "definition": (
                "The agent successfully combines two or more separate facts stated in "
                "different turns into a single logical deduction or recommendation."
            ),
        },
        {
            "name": "re_asks_attribute_user_already_provided",
            "type": "negative",
            "definition": (
                "The agent explicitly asks for an attribute the user already "
                "provided in a previous turn of the conversation."
            ),
        },
        {
            "name": "asks_question_already_answered_implicitly",
            "type": "negative",
            "definition": (
                "The agent asks a question that is rendered unnecessary by "
                "something the user already stated earlier in the conversation."
            ),
        },
        {
            "name": "fails_to_infer_obvious_implication_from_user_context",
            "type": "negative",
            "definition": (
                "The user provides a clear contextual fact earlier in the conversation, "
                "but the agent later fails to deduce the obvious implication and asks "
                "a redundant question anyway (e.g., user said 'I'm doing a 10-day "
                "backpacking trip'; agent later asks 'Are you looking for lightweight gear?')."
            ),
        },
    ],

    "drift_avoidance": [
        {
            "name": "abandons_primary_goal_to_chase_secondary_concern",
            "type": "negative",
            "definition": (
                "The user states a primary goal but mentions a secondary concern in "
                "passing, and the agent completely pivots to the minor concern, "
                "abandoning the primary intent."
            ),
        },
        {
            "name": "wastes_full_turn_on_off_topic_chat",
            "type": "negative",
            "definition": (
                "The agent spends a full conversational turn engaging in "
                "non-transactional dialogue without driving the conversation back "
                "to the gear-finding funnel."
            ),
        },
        {
            "name": "gives_medical_or_training_advice_instead_of_gear",
            "type": "negative",
            "definition": (
                "The agent drifts away from gear recommendations and starts giving "
                "medical advice, training plans, or physiotherapy suggestions."
            ),
        },
        {
            "name": "recommends_or_discusses_non_nto_products",
            "type": "negative",
            "definition": (
                "The agent gets distracted by a user mentioning a competitor's "
                "product and either recommends that competitor or discusses "
                "products outside the brand's own catalog."
            ),
        },
        {
            "name": "promotes_add_ons_before_primary_goal_resolved",
            "type": "negative",
            "definition": (
                "The agent tries to sell complementary items before the primary "
                "goal is resolved."
            ),
        },
    ],

    "constraint_satisfaction": [
        {
            "name": "soft_constraint_violation",
            "type": "negative",
            "definition": (
                "A returned product misses a stylistic, semantic, or use-case "
                "requirement (e.g., wrong activity type or wrong vibe)."
            ),
        },
        {
            "name": "hard_constraint_violation",
            "type": "negative",
            "definition": (
                "A returned product explicitly contradicts a binary, non-negotiable "
                "filter stated by the user (e.g., wrong gender, wrong category, "
                "over budget)."
            ),
        },
        {
            "name": "returns_wrong_product_type_entirely",
            "type": "negative",
            "definition": (
                "The system returns the right attributes but the wrong foundational "
                "item (e.g., recommending a hiking pole when the user asked for "
                "hiking boots)."
            ),
        },
        {
            "name": "filters_on_constraint_user_never_stated",
            "type": "negative",
            "definition": (
                "The system over-filters based on a constraint the user never "
                "actually mentioned."
            ),
        },
    ],

    # ── NDCG metric (computed from product relevance) ────────────────────────

    "product_relevancy": [
        {
            "name": "ndcg_at_3",
            "type": "positive",
            "definition": (
                "Measures whether the top-3 products shown are relevant to the user's "
                "query. Each product is scored on title similarity, price match, and "
                "feature overlap, then weighted by relationship type "
                "(exact=1.0, substitute=0.9, complement=0.65, irrelevant=0.0). "
                "Final score is NDCG@3 — a position-discounted average where rank 1 "
                "matters more than rank 3."
            ),
        },
    ],
}

# Which scale each metric uses:
#   binary → Yes/No/NA verdict, 0.0 or 1.0
#   likert → 1-5 with improvement comment; normalised (score-1)/4
#   ndcg   → NDCG@3 computed from structured product scoring
METRIC_SCALES: dict[str, str] = {
    "cognitive_load": "likert",
    "information_gain": "likert",
    "refinement_quality": "likert",
    "tone_persona": "likert",
    "rationale_quality": "likert",
    "goal_identification": "binary",
    "redundancy_avoidance": "binary",
    "drift_avoidance": "binary",
    "constraint_satisfaction": "binary",
    "product_relevancy": "ndcg",
}

# Flat lookup: proxy_name -> (metric, proxy_dict)
PROXY_INDEX: dict[str, tuple[str, dict]] = {
    proxy["name"]: (metric, proxy)
    for metric, proxies in METRICS.items()
    for proxy in proxies
}
