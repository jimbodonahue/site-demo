from math import ceil

from django.db import models

# from rest_framework.pagination import PageNumberPagination
# from rest_framework.response import Response


class TimeStampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# class CustomStockPagination(PageNumberPagination):
class CustomStockPagination:
    page_size = 100
    page_size_query_param = "per_page"
    max_page_size = 1000

    def get_paginated_response(self, data):
        total_stocks = self.page.paginator.count
        page_size = self.get_page_size(self.request)
        total_pages = ceil(total_stocks / page_size)
        current_page = self.page.number

        return Response(
            {
                "total_rows": total_stocks,
                "total_pages": total_pages,
                "current_page": current_page,
                "has_next": self.page.has_next(),
                "has_previous": self.page.has_previous(),
                "page_size": page_size,
                "results": data,
            }
        )
