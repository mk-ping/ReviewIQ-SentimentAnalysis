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

ISSUE_DISTANCE = 0.6      # cosine distance below which two complaints join one issue (tune on gold set)
ISSUE_MIN_REVIEWS = 2     # an issue needs this many distinct reviews (raise to 5 on real data)
GROWTH_MIN = 0.5
GROWTH_MAX = 2.0
GAIN_FLOOR = 0.01         # keeps priority above zero when ratings are missing
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

SPIKE_Z = 2.5             # weekly negative-mention count this many standard deviations above its mean raises an alert
SPIKE_MIN_WEEKS = 4       # earlier weeks of history needed before an alert can fire

SPIKE_MIN_COUNT = 3       # a weekly count below this never raises an alert, however flat the history

TIEBREAK_SAMPLE = 300      # rows scored for the rating-vs-votes correlation
TIEBREAK_TRACKS = 0.3      # Spearman at or above this: the column moves with text sentiment (a rating)
TIEBREAK_FLAT = 0.15       # |Spearman| below this: unrelated to sentiment (votes, counts)
TIEBREAK_WEAK_HEADER = 0.8 # only columns chosen with a header score below this are tested
