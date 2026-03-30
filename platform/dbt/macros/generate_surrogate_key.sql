{% macro generate_surrogate_key(field_list) %}
    {# Thin wrapper — dbt_utils provides this, but kept here for reference #}
    {{ dbt_utils.generate_surrogate_key(field_list) }}
{% endmacro %}
