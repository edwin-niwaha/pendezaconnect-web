from urllib.parse import urljoin, urlsplit, urlunsplit


def absolute_media_url(serializer, value):
    """Return a public HTTPS URL for FileField, CloudinaryField, or stored URLs."""
    if not value:
        return None
    raw_value = str(value)
    if urlsplit(raw_value).scheme:
        url = raw_value
    else:
        try:
            url = value.url
        except (AttributeError, ValueError):
            url = raw_value
    if not url or url == "default.jpg":
        return None

    request = serializer.context.get("request")
    if request and not urlsplit(url).scheme:
        url = request.build_absolute_uri(urljoin("/", url))

    parts = urlsplit(url)
    if parts.scheme == "http":
        url = urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    return url


def thumbnail_url(serializer, value, size=192):
    url = absolute_media_url(serializer, value)
    if not url or "res.cloudinary.com" not in url or "/upload/" not in url:
        return url
    transformation = f"c_fill,f_auto,h_{size},q_auto,w_{size}"
    return url.replace("/upload/", f"/upload/{transformation}/", 1)
