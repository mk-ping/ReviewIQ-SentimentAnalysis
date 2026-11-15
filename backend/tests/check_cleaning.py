from app.services.cleaning import clean_text, spam_score

assert clean_text("Loved it!!!!!") == "Loved it!!", clean_text("Loved it!!!!!")
assert clean_text("sooooo good") == "soo good"
assert clean_text("sooo good") == "sooo good", "3 repeats stay; the rule starts at 4"
assert clean_text("<b>Great</b> &amp; cheap") == "Great & cheap"
assert clean_text("thx gr8 pls") == "thanks great please"
assert clean_text("bekar quality") == "useless quality"
assert clean_text("Mail a@b.com or call +91 98765 43210 see https://x.com") == "Mail [EMAIL] or call [PHONE] see [URL]"
assert "heart" in clean_text("love it \U0001F60D")

assert spam_score("x", "see [URL]") == 0.4
assert spam_score("x", "Click here to buy now at [URL]") == 0.7
assert spam_score("x", "Very nice product") == 0.0
assert spam_score("x", "good good good good good good") == 0.2
print("cleaning checks passed")
