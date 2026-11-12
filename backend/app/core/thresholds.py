STAR_GAP_FLAG = 1.5       # |expected stars - customer stars| at or above this is a big gap
MISMATCH_DIFF = 0.7       # |text score - star score| at or above this
MISMATCH_MIN_CONF = 0.7   # model must be at least this confident
FUSION_W_MIN = 0.4
FUSION_W_MAX = 0.9
SPAM_MAX = 0.6            # reviews above this spam score are left out of True Rating
TRUE_RATING_M = 30        # smoothing, same as the weighted rating
LOW_SAMPLE = 30           # UI warns below this many reviews
BOOTSTRAP_N = 500

ASPECT_LLM_CONF = 0.8     # placeholder confidence for LLM-labelled mentions (not calibrated)
ASPECT_MIN_CONF = 0.6     # mentions below this are ignored by the aspect views
NEG_MENTION = -0.25       # sentiment at or below this counts as a negative mention
HIDDEN_MIN_STARS = 4      # Hidden Dissatisfaction looks inside reviews rated this or higher
