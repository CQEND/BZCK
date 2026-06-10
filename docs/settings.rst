.. _settings:

Settings
========

Settings are configurable in ``settings.py`` in the scope ``SPECTACULAR_SETTINGS``.
You can override any setting, otherwise the defaults below are used.


.. literalinclude:: ../drf_spectacular/settings.py
   :start-after: APISettings
   :end-before: IMPORT_STRINGS

Django Rest Framework settings
------------------------------

Some of the `Django Rest Framework settings <https://www.django-rest-framework.org/api-guide/settings/>`_
also impact the schema generation.  Refer to the documentation for the version that you are using.

Settings which effect the processing of requests and data types of responses will usually be effective.

There is explicit use of these settings:

- ``DEFAULT_SCHEMA_CLASS``
- ``COERCE_DECIMAL_TO_STRING``
- ``UPLOADED_FILES_USE_URL``
- ``URL_FORMAT_OVERRIDE``
- ``FORMAT_SUFFIX_KWARG``

The following settings are ignored:

- ``SCHEMA_COERCE_METHOD_NAMES``

The following are known to be effective:

- ``SCHEMA_COERCE_PATH_PK``

Example: SwaggerUI settings
---------------------------

We currently support passing through all basic SwaggerUI `configuration parameters <https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/>`_.
For more customization options (e.g. CSS, JS functions), you can extend or override the
`SwaggerUI template <https://github.com/tfranzel/drf-spectacular/blob/master/drf_spectacular/templates/drf_spectacular/swagger_ui.html>`_
in your project files.

.. code:: python

    SPECTACULAR_SETTINGS = {
        ...
        # available SwaggerUI configuration parameters
        # https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/
        "SWAGGER_UI_SETTINGS": {
            "deepLinking": True,
            "persistAuthorization": True,
            "displayOperationId": True,
            ...
        },
        # available SwaggerUI versions: https://github.com/swagger-api/swagger-ui/releases
        "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest", # default
        "SWAGGER_UI_FAVICON_HREF": settings.STATIC_URL + "your_company_favicon.png", # default is swagger favicon
        ...
    }

Example: Redoc UI settings
--------------------------

All basic Redoc `configuration parameters <https://redocly.com/docs/redoc/config/>`_ are
passed through via ``REDOC_UI_SETTINGS``.

You may also override the Redoc template path for full control over the rendered HTML
(e.g. to add a company logo, change the document title, or inject custom JavaScript).
Place a custom template in your project's ``templates/`` directory and point to it:

.. code:: python

    SPECTACULAR_SETTINGS = {
        ...
        # pass configuration to Redoc.init()
        "REDOC_UI_SETTINGS": {
            "expandSingleSchemaField": True,
            "hideLoading": True,
            ...
        },
        # host your own Redoc bundle: https://github.com/Redocly/redoc/releases
        "REDOC_DIST": "https://cdn.jsdelivr.net/npm/redoc@latest",  # default
        # override the default template to customize the rendered page
        "REDOC_TEMPLATE_NAME": "my_project/redoc.html",  # default is "drf_spectacular/redoc.html"
        ...
    }

The default template lives at
`drf_spectacular/templates/drf_spectacular/redoc.html <https://github.com/tfranzel/drf-spectacular/blob/master/drf_spectacular/templates/drf_spectacular/redoc.html>`_.
