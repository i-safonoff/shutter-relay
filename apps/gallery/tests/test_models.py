from apps.gallery.models import Album, Photo


def test_s3_key_namespaces_by_album_slug():
    album = Album(slug="trip-to-lisbon", name="Trip to Lisbon")
    photo = Photo(album=album, object_key="abc123")
    assert photo.s3_key() == "trip-to-lisbon/abc123"


def test_object_key_defaults_are_random_and_do_not_collide():
    keys = {
        Photo(album=Album(slug="x"))._meta.get_field("object_key").get_default() for _ in range(50)
    }
    assert len(keys) == 50
