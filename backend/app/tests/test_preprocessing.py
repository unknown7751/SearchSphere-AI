import pytest

from app.services.preprocessing import PreprocessConfig, Preprocessor


def test_lowercasing(preprocessor):
    assert preprocessor.normalize("PyThOn IS Great") == "python is great"


def test_punctuation_removed_and_spaces_collapsed(preprocessor):
    assert preprocessor.normalize("Hello,   world!!  (test) -- ok?") == "hello world test ok"


def test_tokenization(preprocessor):
    assert preprocessor.tokenize("Machine-learning, deep learning.") == ["machine", "learning", "deep", "learning"]


def test_stop_word_removal(preprocessor):
    r = preprocessor.analyze("The cat is on the mat")
    assert r.tokens == ["the", "cat", "is", "on", "the", "mat"]
    assert r.stop_words_removed == ["the", "is", "on", "the"]
    assert r.tokens_without_stopwords == ["cat", "mat"]


def test_stemming(preprocessor):
    r = preprocessor.analyze("Learning algorithms computers")
    assert r.stemmed_tokens == ["learn", "algorithm", "comput"]


def test_lemmatization(preprocessor):
    r = preprocessor.analyze("studies running algorithms mice")
    assert r.lemmatized_tokens == ["study", "run", "algorithm", "mouse"]


def test_all_stages_exposed(preprocessor):
    r = preprocessor.analyze("The Quick, Brown Foxes!")
    assert r.original == "The Quick, Brown Foxes!"
    assert r.normalized == "the quick brown foxes"
    assert r.tokens == ["the", "quick", "brown", "foxes"]
    assert r.stop_words_removed == ["the"]
    assert r.stemmed_tokens == ["quick", "brown", "fox"]
    assert r.lemmatized_tokens == ["quick", "brown", "fox"]
    assert r.index_terms == ["quick", "brown", "fox"]


@pytest.mark.parametrize("text", ["", "   ", "?!...", "()[]{}", None])
def test_empty_or_punctuation_only(preprocessor, text):
    r = preprocessor.analyze(text)
    assert r.normalized == ""
    assert r.tokens == [] and r.index_terms == [] and r.stop_words_removed == []


def test_unicode(preprocessor):
    assert preprocessor.normalize("Café NAÏVE") == "café naïve"
    assert preprocessor.normalize("ﬁne") == "fine"  # NFKC folds the fi ligature
    assert preprocessor.tokenize("Café") == ["café"]


def test_numbers_are_kept(preprocessor):
    r = preprocessor.analyze("Python 3.12 released in 2024")
    assert r.tokens == ["python", "3", "12", "released", "in", "2024"]
    assert r.tokens_without_stopwords == ["python", "3", "12", "released", "2024"]
    assert r.stemmed_tokens[-1] == "2024"


def test_unknown_words_pass_through(preprocessor):
    r = preprocessor.analyze("zxqvt")
    assert r.tokens == ["zxqvt"]
    assert r.lemmatized_tokens == ["zxqvt"]


def test_documents_and_queries_use_identical_pipeline(preprocessor):
    assert preprocessor.index_terms("Machine Learning Algorithms") == ["machin", "learn", "algorithm"]
    assert preprocessor.index_terms("machine   LEARNING, algorithms!") == ["machin", "learn", "algorithm"]


def test_lemma_index_form():
    lemma_pre = Preprocessor(PreprocessConfig(index_form="lemma"))
    assert lemma_pre.index_terms("studies running") == ["study", "run"]


def test_invalid_config():
    with pytest.raises(ValueError):
        PreprocessConfig(index_form="soundex")
