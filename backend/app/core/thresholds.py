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

TIEBREAK_SAMPLE = 300       # rows used to test a column against text sentiment
TIEBREAK_WEAK_HEADER = 0.6  # a rating or helpful column with a weaker header match gets tested
TIEBREAK_TRACKS = 0.3       # correlation at or above this: the column moves with sentiment (a rating)
TIEBREAK_FLAT = 0.1         # correlation within +/- this: the column ignores sentiment (votes, counts)

LISTING_TOP_K = 20        # nearest reviews examined per claim (plan starting value: 30)
LISTING_MIN_SIM = 0.30    # best sentence must be at least this similar to the claim
LISTING_MIN_EVIDENCE = 5  # supports + contradicts needed for a verdict
LISTING_CONFIRM = 0.70    # support share at or above: confirmed
LISTING_CONTRADICT = 0.30 # support share at or below: contradicted

SPIKE_Z = 2.5             # weekly count this many std above earlier weeks raises an alert
SPIKE_MIN_WEEKS = 4       # earlier weeks needed before any alert can fire
SPIKE_MIN_COUNT = 5       # latest week needs at least this many complaints

MIN_VAL_PER_GROUP = 100   # a route group with fewer validation reviews uses equal ensemble weights

ASPECT_SIM = 0.35         # a sentence gets every aspect whose cosine similarity is at least this (recheck for multilingual SBERT)
SBERT_EN_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # English sentences; others use EMBED_MODEL

ISSUE_MIN_SENTENCES = 30  # an aspect needs this many problem sentences before KMeans runs; fewer become one 'few sentences' issue
ISSUE_K_MIN = 2           # KMeans k range, the silhouette score picks k
ISSUE_K_MAX = 4
ISSUE_RARE_STD = 2.0      # a sentence farther than mean + this many std from its cluster centre is a rare complaint
KMEANS_SEED = 42
