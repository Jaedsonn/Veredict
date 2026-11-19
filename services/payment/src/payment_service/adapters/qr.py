"""QR Code do PIX em SVG, gerado na hora a partir do copia-e-cola (nada vai para o banco)"""

import io

import segno


class SegnoQrRenderer:
    def svg(self, payload: str) -> str:
        buffer = io.BytesIO()
        # Correção M e borda de 2 módulos: lê bem em tela, com tamanho controlado pelo CSS
        segno.make(payload, error="m", micro=False).save(
            buffer, kind="svg", scale=4, border=2, xmldecl=False, svgns=True, omitsize=True
        )
        return buffer.getvalue().decode()
