"""Application icon and the per-user desktop entry that lets Wayland taskbars find it."""

import base64
import contextlib
import os
import sys
import warnings

from PySide6.QtGui import QIcon, QPixmap

from umbriel_core.paths import LEGACY_DIR_NAME, write_text_file

from . import APP_NAME

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCHER_PATH = os.path.join(os.path.dirname(PACKAGE_DIR), "umbriel-settings.py")
APP_ICON_PATH = os.path.join(PACKAGE_DIR, "assets", "icon.jpg")

_APP_ICON_DATA = (
    "/9j/4AAQSkZJRgABAQEAZABkAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMU"
    "FRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBQUFBT/wAARCADxAQADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD8+WyTilxmmsTnil5bHavTJHLzinlqjU4OMU89KTAN2SR2p2emKjzgU4HJo6AP6DOaUGmZ"
    "NOFCAcTQOtAGetGOfSmikPDEUM25aKQDr61d+oxME9DQV71Mi5FL5YwaL2C1ysKUZBqTZzQUFNsQ3rTKk25o2Cpv0Ai6imjipCuD"
    "TNpHPWpuSNJpu72p22kK4FIBCc00nNKaTtQAAZpAce1A5wKCfm60wH4IqKSpScA1E1JAMA70jDjNLQ3zAUxMYOBT4zmRfrTT+lLG"
    "f3g+tNbgWDwetKPrTWzmlPFIYoGCKcD2NIM4zSjmkAjCnL0FITgUo6c0AOI+lBbAGaEAJFOYDnBoQCqMmginRjj3phmzKsUStNMx"
    "CrGgyST0H1qlFy2GSAc05kAP1r01P2Wfiu3gufxQfDE0NnEvm/YpCBdvH1LCH73HocN6A15Ut9EyZYlXHBXHNZ0atLEX9hNTs7Oz"
    "vZ+ZrOMoL301fuXF6U7IFbvg74YeNfiK6/8ACM+F9R1SInb9pSEiEH3kOEH4mvbvC37APxH1tUk1rU9J8PRH70ZlM8y/gg2/+P1x"
    "YrMMDgtMTXjF9r6/ctTalQrVv4cGzxT4YfD67+LPxJ0TwlaXBtDfykS3ITf5MaqXdsZGcKpwMjJwM19fL/wTf8KImZ/F2tSkDkxx"
    "RJ/MGu3/AGfP2PbP4F+LZPEcviSXxBftavbIjWYgSPcVJYfOxJwpH0Y19CyH92w9q/LM/wCLa0sTGGVVrU0t0t313Vz6PBZZBQbx"
    "Efeufnq/7HPh4g+Xr+qJ7usZ/oK8R+K3w4l+FPi6PSvtr6hZ3EAnguHTYSCSCCMnkFf1Ffdnc/WvMfjR8Fl+LKaZJHqQ0u7sPMCu"
    "YPMEgbbwfmGMFevPU1tk3E+Iji1HMK16bTvdbdnorm2NyulKlfDwtI+NT0o6V6h4j/Zn8c6CjPaJaa3CvP8AosuHx/uvt59gTXme"
    "o2GoaHcm21bT7rTZx/BcxMh+uCBX6nh8VhsYr4aop+j1+7c+Rq0KtH+JForkCmkcU4EMMg8eopp5rptZmA1gDTSePWnn3qPbzigB"
    "FPNKRQFwaMcjNHQAJ9aYccHNPYc8VGy0INxC2aMDGKCOOaFAIHegQYytJGuJB9adg0L99R7009QJOaVTmk5xTh19qBi9KFHpS0o4"
    "OKQIPrRilNG0HrzSAdEMH2p4ALHimqeKXvkUAdP8LvhtrHxg8eWXhTRHhgubhWkee4bCRRqMsxxycDsOSa/R34JfsreDPgnFFd29"
    "sNZ8RgfPrF6gLqe/lLyIx16ZbnljXwP+zBq2p6P+0H4Qu9Is7jUJftIhuIbZSx8lwUlY47KrFsngba/Vt2+Y81+Vcc5hjMPUp4Sl"
    "Plpyjdpbt369T6jJ6FKcXVkryTFJz3rzA/s0/DSTxpeeKZfCdjcatdOJH89S8Afu4hPybieScdeepOfS92O9cR43+MXhzwNZy3F9"
    "fQ7I/vO0gSNT6Fzxn2GTX5bhK2LhJwwspJy0dr6/cfSzhTkrzS07ncQxxwRJFEixRoNqogwFA7AUy5vILNN880cKf3pHCj9a+J/i"
    "N+3vaRtLB4einvz0DQf6PF/32wLn8ABXz94m/as8eeIJXaK7g0xW/wCfeLe+PdpNxz7jFfZYLgrNsd79SPIn1k/03PLrZrhaOid/"
    "Q/UC58d6FbE79RiJH/PMF/5A1nXPxN0KNCftEjL0yIyP51+SmofEXxbr8oS68RapclzgR/an2kn0UHH6V9Q6T+zB4UOnWrasdQvd"
    "Q8pftLSXjYMmBuxjtnOK6sx4Uw+TRg8biNZbKMb7erQsNmMsY2qNPbu7f5ntKyK/zKwIPoacSCOlfInxa0T4c/DGaSx0ganc68R/"
    "qbe/Kx257GRsE577Rz7jivMtK+I3jPTF/wBC8RarFHjAU3Tso+gJxXo4Xg6eOoLEUatk9uaNr/izOrnEaE/Z1I3fk7n3P4q8e+H/"
    "AARb+frmqW9gpGVR2zI/+6gyx/AV80/Gn9ozT/HWi3Wg6LpLPbTEA3t6AHGGBzGgzg8dSc4PSvFbpbvVryS71C6lu7iQ7nlmcu7H"
    "1LHk0qwrDwoAr7HLOGMFlk41qknUqLXskzxcVm1bEJwiuWL+8SBDFbqD1p4fmhuaAvWvq5Pmd2eLawHB71HnFKeM+tJjJxSADzRm"
    "g0h96LAFNzz70pOBSDG0/wB7tQAhANM6HgcU7tyeO9A5oAOacn+sX60U2MgyA01uA8HHWnHPBoKilGWAoYDl5HNKfWmrTxzxSAFO"
    "RTgO9NwRTDdRqcbufamouXwoCUflXRfDn4d698WvFtr4b8OWv2i7m+aSVuI4Ix96R27KP1yAMkgVkaBoWo+MddsND0O2e+1O/lEM"
    "MMfUsf5DuSeAASa/Uv8AZ9+BelfArwVFp1usdxrdyqyalqIHM0mPuqTyEXJCj6nqTXzWf53TyPD829WXwr9X5fmelgcFLGT10it3"
    "+hJ8CvgD4c+BHh0WemRi71idR9u1WVR5s7eg/uoD0Ufjk813mu+ILLw9aNc3swjX+FByzn0A71R8X+MLLwfpj3V0679pKRs23OOp"
    "J7AdzX50/tEftP6h8QdRutL0W7dNOOY5ryMlTMO6R/3Y/fq306/juWZVj+J8Y6k23fWUn0/roj66vXoZdRWluyPdPil+1DqvizW5"
    "fC3w/tBrGp4PmeW/+jW6g4LSPkbsZGQCF5AyTxXE3H7PU3jSwnuvG/iS81XXZYyImtzttrNj/cTHI9fu554zzXhX7NuvyeH/AIr6"
    "Wqq7xXwezlVASdrDIP0DKpPsDX2B438a6R4D0WTVNXuhBAvCIOZJW/uovc/5OBX12Z4Wtw/iqeByyPvSSfMleTfbyXkvmcOFqwx1"
    "KVfEPRdOiPi7UvgV4zsfE0+jQ6LPeSRnIuYhiB0PR/MOFAPuQeo7VZu/hr4e8KJ/xU/i2D7Yv3tM0SL7VMD/AHWclUQ/Umuk8S/G"
    "Hxt8b9ZHh3wxZXMFtcEqlhYZM0q+srjoPXoo75616v8ADT9gmVlivfHWrmDPzHTNLYEj2eUgj6hQfZq/XMDRzTFUoyxklTdtVHf5"
    "t3S9EvmfKVnhqc2qC5vN7fd/mfN0Hifwz4fvYbnR/DMl3PbyCSK41m9Z/mByCY4gg69iSK7hf2jviTr7MdPghJ9LOwMmPz3V9r+H"
    "fhN8L/h9Giad4f0sTJ/y2mi+1TZ/333EfmK6v/hL9Mt1CRQy7F4ARAAPwzXrS4fwuJalXpc7XWV3+ZjHF1qatCXKvLQ/KnVdF1uK"
    "4lvNS0++SWRzJJLdQONzE5JJI9appfv0ZQcehxX6xL42sW4MU4H+6P8AGsPX/CvgDxwjJrGh6Xeu/WS5tFEg+j4yPwNenPL3azho"
    "jl5tb3PzAS9ic8nYfepGGec5U19peP8A9hbwxrlvJdeD9Tm0S6IJS2uHNxat7ZPzr9ct9K+S/iF8KvFnwk1QWniDTXtY3JEN0nz2"
    "8+P7jjjPfHBHcCvIq4Fx1gaKTW5z/U0jGkiuFm9m7inNXlSi4u0jRO5GRmkb1pzZ6c009fWkMTr9KUn060AUjcYoAa3YULSY5zTu"
    "duR0pANYYpAKASzDNOJyaYAT1xSQjMg+tI3XmpIAPMX60IBTxQODSjmgelAC9KevqaZnJIpwFADZ3KqAPvNwK/R39nT9lLwt4W+F"
    "lovi/wANadrOv6ogurs6hbLK9sGGUhQsMoVBGcYO4nnAGPkf9kX4Yx/FL426el4gk0rRkOp3SNyJPLZQie+ZGXI/ug1+ojNk1+X8"
    "a5xUw3s8Bh5NP4pNaei/X7j6bJ8JGadeor9F+p5v4E/Z0+H/AMM/FUviLw3oKadqUkLQ7vOkkVFYjcUV2IUnGMjHGR3NdzrutwaD"
    "ps17OflQfKg6u3ZRV5mwOe9fJP7VvxY1Ge5svC/hlzJq+qSG0tBGeUXpJNkdPQHsAT2NfmuGpYrOsVGNWbk+7d7JefZH0cnTwtNu"
    "Ksuy7nhH7Uv7Qd5431q80HTrk/ZEYx3k0R+WQg/6pf8AYXv6n9fB/DfhvUPFes22l6Xbtc3lw21EXt6knsAOSa+mtS/ZD0W60u3F"
    "lrN3aaksSiWSVFlikfHJ28FQT7nFdr8IvhTp/wAINDupruaG41KQM11qBG1UjHIVc9FAGT6n6DH7LQ4iyrKcu9jlvvTWiVrXfd+X"
    "/DHy9TLsVi8Rz4nSP5LsYmheGvDP7NvgebV9QKXmsyJsecD95NIRkRRZ+6vHJ9snsB434U8KeMv2qfiG7PIYrGEgz3TA/Z7CEnhV"
    "HdjjgdWPJIGSE8SXutftL/F600fRN32IyGG0VwdkEIOXncdsgZP/AAFfSvtfw3oWk/C3wla+FfDSeVBbj/SLvA8yeU/fdj3Jx+Aw"
    "BwBX2nDWRVU/ruM96vPVt/ZXZdv6R5WPxcZ/uaOlOP4+ZN4I8FeEvgjog0rw3YrJdsB9pu5MNNOw7yP/ACUcD0FS3+tXmqE+fMdn"
    "/PNeF/L/ABqgDQWxX6tSw9OitFdnhuTY48Gkzmm7uaXIrpIFzzRmm0uaALFrez2b7oJXib/ZPB+o71qX15pXjHSJ9G8S6fBfWNwu"
    "2RJU3I3uR2I7Ecg8jFYYalHJrCrQhVXvIpScT5G/aL/Zgu/hQ7eIPD7S6j4TkYEsfmlsiTwrkdUOcB/wPOCfELe4Eww33x29a/Tm"
    "y1GP7LNp9/Cl5pdyhimt5VDKVYYYYPUEHkV8L/tI/BRvg54vjm07dL4a1PdNp8x+by/70LHuVyMHupHfNfJY/AOP+Z0Rl1R5iRzT"
    "SKEkEqBh36ijrXyrTTszp3FUZ7UwnnFL60w9aAFPQ0fe+lH60nHWgBQMUHp/WgnIpCDS6jEHJp8XEi/WmYwKFb5x7GjdgSLxxS4y"
    "DTWXnrSqetPzEB4IqVW3DrzTAaOhpMDqvhj8Tdc+DfjG28SaBMqzp8k8EnMdxESC0bjuDge4IBHIr9Vfhd4/g+KPgDRvFNtZz2EO"
    "oxGQW9xjchDFWGR1GVOD3GDgZr8i9F0m48Sa9pej2q7rrULmO2iB7u7BV/Uiv2J8NeH7Xwj4a0vRLJdtpp1rFaxDGPlRQo/lX5Xx"
    "9HDqnQm4/vXfX+6u/wA9j6fJHUbmr+6vzMb4l+JE8N+GLmYyiGSRSocnGxcEu34DPPuK/OrwH8bLCX43XviDX0xZXaNZWlw//LlH"
    "u+U49CB8xHTcT619B/tyfEd9J8NT6ZbS7ZbphYLg87SN0x/LCH618H6bp8+sahbWVsnmXNzIsMSD+JmOAPzNdvB+RUq2W1sRidFU"
    "TV+y6v8ArsGa46dKvCnS6a/M/SBHWRFkjYPG4DKynIYHoQa8V/an8c/2D4Li0O2k2XursVfB5WBcbvzO0e43V6t4S0FPCnhnS9HR"
    "zIllbpD5jHO4gcn8Tk18o/F3zvid+0DFoVvIfL+0waVE3ZBuAkb8GZz9BXhcKZbDG5ukvehTu/Wzsv8AM9HNcRKjhOzlp/me5/sm"
    "eA/+ED+HcniS4i2634iH7liPmhs1Py49N7At7gJ6V62ad5cMEcVvbRiG0t41ggiHRI0AVF/AAU2v65w9FUaaitz82k7sM8UmM+1H"
    "U0tdRIAUY5oDY4paAFwKawoBxS0ANxSgYpScmgdaACsb4i+CYPir8PtT8K3O37Q6mfTZn/5Y3KglOewblT7MfWtgnBpySFWDKdrA"
    "5BFZVaaqxcWNOzPzRSKWyvJrWdGilRijxuMFWBwQffipz8tem/tS+FU8MfF29vIECW2sRpqaADgOxKyj/v4jn6MK8xPzgHt2r82x"
    "1J0qup203dWGjJPFKUzSgU3PGK865qIAQAKUjFG3JFLipbBDTwc0ZzSMecYzQDTGDU2PBkH1oJzSrww9c01uBIRSEYFLuyO1GN1M"
    "QKd3anAZpoXmkedEOD970FNRcnZAe0fsdeFB4q/aG8Ol03waaJNQk46eWh2H/v4yV+nt1MtvbyTOcIilmPoBXwx/wTn8OTP4q8Wa"
    "9LbypDFYx2kUroQreZJuYKe+PKGcetfaHjO6Nr4X1JwQMxGPP+98v9a/C+Na/t82jRT0hFL9X+Z9tk9Plw3N3dz82f2vvFMmvfEW"
    "3si+5bSAyuvpLKxZv/HQlYf7Mnhn+3fija3Lruh0yF7xs9NwwqfjuYH/AIDXM/GLVf7X+KPia43bgt68AOe0f7sf+g17l+x/owi0"
    "LX9WZctPcJbIxHQIu44/7+D8q/U8dL+yuGVCOj5EvnLf82fP0F9bzPme12/uPoR2AQkkAAZJPavj/wDZ4B8TfHwapIC+03d8c+rB"
    "lz+cgr6T+LOtf8I/8N/EN6r+XItnJHG2cEOw2rj8WFfPP7H4U/EnUmP3hpUmP+/sVcHhrhveqV31aX3anXxDU96FNebPr80gFL1o"
    "zX9GnxYYxQDmk6mloAAM0vSjpSZ5oATFKTjigGlNACdRRjFGaTrQAdacP1pDxSZoA+a/2z9ND2vhfUAPmR57dj6ghGUfhhvzr5tg"
    "O6FT7V9W/tjIrfD7R5D95dUUD8YpP8K+T7diIBxmvhs7ilUuvI6qQ8nFNxml2jrmg18w2dSF6Cm7sdqXOB600cVNuoCHJOaQ8jH6"
    "044po4q9gAcULzIv1pGbmli+8PrSQD2O1silUgUh+bvSYB4piJQQelfXH/BPf4ceHvFcni/XNb0e01a5sXtobM3sIlWEsJGdlVsj"
    "dwnPUY46mvkVTjg19w/8E2mB8L+OVHUXlsfzR/8ACvmuJqs6OTV5U3Z+7t6o9PLYqeLgpLufYqosaKiKERRgKowAPQCuW+JbmPwp"
    "OB/HIi/+PZ/pXVZrkviaN3hhsZ+WVCfzr+dsM+atFy7n3z0Wh+a3gb4F6t8XbzVNdXULfTtLfUJo2ldS8rNu3EqgwCPmHVhX0/8A"
    "DX4fWvw08Mro1rcy3iea0zzTAKWZsZ4HQcD1rif2XriFPAeo2nmr9oh1W4DxbhuH3cHHpXsL5xX6PxJmuMr15YGb/dxasrdtjyct"
    "wtGnTVeK95nxt8T18Z/E3xh4o+ypeatpWh3r2621vysKhnVSIxyxOxsnBP6VX/Zz8R2ngv4opLrE66ZbSW0trJJc/IEYlSN2enKj"
    "rXsv7P3y+OvikjfeGq5I/wC2s9ep+I/BegeL4fK1jSLS/wCMB5YxvUezj5h+Br7SlxdDIcRHBuiuSCjZrR6xT22f4HjvKpY6Drqf"
    "vNvf1Nyw1Sx1aAT2F5b3sB6S28qyKfxBIqwRXG6N+xJ4V1nS01bQdf1vwrqJZlDWs/mRrg8cHD+n8dc949+FPxi+C/hy/wDEFr40"
    "svFeh6annTw30JE5QEZOCCTgcn95nHSv0fL+P8mx040udxm9LNdfy/E8SvlGKoJycbpdj1PGKKyvCXiCLxZ4X0rWIkEa3tsk5jBz"
    "sJHK59jkfhWt0r9JTTV0eKApCaCaVeDVCBV5pW4pC1A55oATFHSl6UDmgAAoxilPSm5GOeMUD3PnH9svVAuj+HNO3fNJPJcEf7qh"
    "R/6Ga+ZLcYhX1616t+1L4mGu/ENLWJ98VjbhMejMc/8AoOw15Yo2oo9BXwOcVOaq0v6sddJCYoyRRuxSYJr506BOTR2pssohX1Y9"
    "qiMkyFDKmFkG5SRjIzjI9sgj8K3jRnOPMieZLQlPUc4pCe1KxwR6UhIBzWBQ0L606P74+tIWyKWL/WLj1FLqApJzmlzmkBGSDSkZ"
    "+lUwHgHPtXrH7Ov7Rmp/s86lqxg0qLWdM1QRi5tpJTE4MZbayOAcHDtkEHPHpXkgYjjipAc49axrUKOKpSw+IjzQlui6dSdKanB2"
    "aP1M+An7R2h/H6DVRpmn3umXemLE1xDd7CpEm7BRlPIGw5yB1Fdv8QIDN4UvsDlQrfkwP8s18Kf8E+/Ei6R8YdT0iRsJqumyKi56"
    "yRsrj/x3zK/QLV7L+0NMu7XGTNEyD6kHFfz/AMRZbSyjNfY0FaDSa67/APBPvMvxEsVQU577M/HzxtBceHviFr8UMklvNb6hOEeN"
    "irAbzggjpxivqf8AZi8U33inwFdDUr6e/vLW9aPzbmQu/llEK8nnu35V4V+0voR0X4rX0uwol/DHcrn1xsb/AMeQ/nXXfsg+IRbe"
    "I9b0V3wt3brcRgn+KM4IH1D5/wCA1+wZ7TjmHD0cTFJyUYyv16XPmcDN4fMXSb0ba/yO5+F+3RPj78Q9IPy/alS9APfJDf8Atava"
    "8YavDfHBPgv9o7wtrjfJY6xB9hmbsZPuDP8A31F+Rr3N+DX5Vnn7yVDEracI/fFcr/I+rwL5VOl/LJ/jqeo/Ci8Eul3lsTlopQ4+"
    "jD/7E1veN/DaeMfBuuaFIQqalZTWhY/w70K5/DOa86+G2r/2f4iSKQ4jul8o+m7qv6jH417BzXx0pyoV41Y7qz+47ZxUk0+p8Tfs"
    "z6y9x4Al0S4Bjv8AQruWzmib7y5YsM/iWX/gNesmvKfiVpQ/Z/8A2kZ9WlHleEvG+XaXokF1kFt3/Azu+kp9DXq9f3VkOZU80y+l"
    "iabvdI/JcTRlh6sqcuggHFBNL0pMetfQnIAGaXpRnFJ15oAMUo4ozSdeBQApNcx498UW/hrQbueeTy1jiaSRu6oBz+J6CtnVdUj0"
    "uHJw0rD5U9fc+1fJP7RvxJOqXjeHrOfzVRhJfSqeC4+7H+HU++B2NceJrqjBvqaRXU8f1jVpvEmv3up3H+suZWmYdduTwB9OB+FM"
    "JJ6cCq9tKiKQRye9SmeP+8K/OsV7SdS9jrg0kOIprMI1yelNadcfL8xru/g/8DfFXxv19bLRbNksY2AutUnUi3tl927tjoo5P0yR"
    "xz5MPTdfEy5ILdvQ1jzVJKFNXbIfgp8I9W+N3j600LT1aK1yJb68xlbWAH5mPv2UdyR2yR0f7VGkab4e+Kg0fSIhBpmn2MNrbxjn"
    "CLuwSe5PUnuSTX6GfDX4R+HfgD8Priw0OMvMIjLd38oHm3coXgt6DPAUcDPqST+b37R2ofbvjLrmDuWHyYc+4iTP6k18hlGeyzvO"
    "Jex0o04u3ntq/wBD2cVglg8GnP45NX/yPOz1phOTQ7du9NB496+sPGFPPFJE+JB7Gmls9+aWIHzAevNPqIn6e9IGK8Um8Dr+tLjP"
    "NJjHAgn3zTwR171FxwRTlPPtQB2XwW8Y/wDCAfF7wnr5fy4LW+jE7HjELHZL/wCOM1frx1GR354r8VJwAuRwQc1+qX7LHxFPxL+C"
    "eg6hPL5uoWaf2deEnJ82IABj7smxj/vV+Yce4NzoUMfFax91/mv1PpckrWlOi/VHzL+3V8P2tZbbW4o8LaTtG5H/ADyl5U/QMCv/"
    "AAKvmP4ceK38E+N9I1hSfKt5h5wHeJvlcf8AfJNfp1+0J4Bh8c+DLq3kX5JIWt5GxkqDyjf8BbB/Gvyv1nSLnw9qt5pt5H5V3ayt"
    "DIh7MDj8q+i4MxtPMsrlgaru43X/AG6zlzilLD4mOIh1/NH2h8fPC48W/DWe8sf317YbdQtJIeSwAy20j1UkjHcCoPhb8e9D8f8A"
    "9maVNJNb+IJIB5kcsWI5JFXL7GBIxwSM4rR+AsWsx/C7R49cTZMqEQK/3/I/5Z7h2OOAPQDvmuN/aM8Jf2NZ6X420OCK01HR7hWm"
    "aJAu9Cw2scdcNgfRj6V8Rh6eGrzlkuId3GUuSaeib6PybS+Z785VKcVjKfVLmX9dUe6qzQyK6sVZTkMOxr3LwvrqeINIhuQR5oGy"
    "VR/C46/4/jXzl4N8U2/jXwpput2uFju4g7IDnY3RlP0YEfhXb+DvFLeGtR3NlrSXCzIPTsw9xXweJw84OVKatKLsewpKcVJbM7T4"
    "yfCbS/jL4EvfDup4jZ/3tpdhctbTgfK4/MgjuCR3r5U+HHj7U/BGvy/Df4gKbDXrAiKyvJj+7vIuiYY9cgfK38XQ/MOft+G4ju4E"
    "mhdZInAZWU5BFeffGj4G+HPjd4fFjrEJgv4ATZ6nAB51ux9P7ynup4PscEfbcG8YVOHq3sK+tKW/k+54OZ5asYueGk1+JwtBrw7W"
    "bD4r/s5ExeILKbxb4Uh+WLV7LMhjTtvzkrx2bA7BjXX+Cvi5Z+ONMa+04LLGjbJEYFHRsZwRz+Y4r+sMBnGDzKkquGqKSfY+Aq0K"
    "lGXLUVmeg7eKXHFc+fFrEcWo/wC/n/1qqzeKLpshEjjHrjJr1Pax7mPKzqGYIhZmCqOSTwBWLqPiWKAFLbEsn98/dH+NcL4u+IOm"
    "eHLcza1q0cRxlYWbLt/uoOT+VeCeNvj1qniuT+yvDNtNZRTt5ayKM3MxPAChfu59sn3FcVfGQpK7dilE7b4y/GxNES40vSrgXOty"
    "ArLODlbb/F/Qdu/pXV/sXfsxz67qNv8AELxhaFtNjbzdLs7lcm6kzkTuD/ADyufvHnoPmufs2/sQXM13beJ/iRamGBSJbfQJPvyH"
    "qGuPQf8ATPqf4scqfuNEWKNI41WONAFVFGAAOgA9K/nXjPjdVFLAZfK7ekpLp5J9+7PsMsyp3VauvRf5ng3xL/Yr+HHxDuZb2Cyn"
    "8M6hISzzaOyxxu3q0RBX/vkKT614h4y/4J1XWl6HqF54f8Wtq9/DEZLfTp7ARGYj+DzfNIBIzj5cZxnHUfR3i79qj4c+BvHD+FdY"
    "1pre/iUedMkLSQQuf+WbsucN0J4wM8kVz/7QP7TmgeBPhdJqfhnWrHV9Y1QNb6abOdJgjY+aU4JwEBzg/wARUetfIZXmPE9CpRoU"
    "+blm1bmV016tbW89j0sTQy6cZzla63s9T8zJ7aS0nkgmjaGaNijxuMMrA4II7EV+rv7PnxH8DeM/AWl6f4NureNdPtY45dM2rFPA"
    "QACXjHXJ53jIJJ5r8o5ZpLmV5ZXaSVyWZ2OSxPJJPrX0/wDsBeBJtZ+J994nkRhZaHasqv0BnlBVR74TzD7HbX6fxnl9LF5Y61ab"
    "i6eqts29LW/LsfOZRXlSxKhCN+Y+2fihq/2PSIrMNhrh8sP9hef54r8nvHutr4k8da7qaNujur2WRD/sbjt/TFfoD+0X4/Sw8J+J"
    "NYSTaLe2a2tCD1dvkQj/AIE2fpX5vRdD718xwFhfY4evin1tFfm/0PUz2peVOl8x7nnNMLYOe9KTnmkHXpX6JsfNAOafAf3i/Wms"
    "eM9KSM5cY9aFcZO3vzSK2BTd2DzRu3e1MCRXGKVajxn2pynHFSM734FfDu0+LPxd0HwtqF61jY3bu0siY3sqRtIVXPG5guAe2c4P"
    "Sv1c8MeFtJ8FaFaaLoljFp2mWiBIbeEYAHqT1JPUk8k8mvx10LX77wn4g03XNLlMGoWFwlxDIOzq2Rn1HHI71+ufwt+Ilh8VvAWk"
    "eJ9OIEd7CDJDnJhlHEkZ91YEe4we9flfH1LEuFCrGT9jtbopd36o+nySVP34te9+h0t3bx3ltLBKu+KVSjKe4NfBf7TXwmj8FeO7"
    "HxpNYLqNha3EX9pW2OJogQEl9+MKc8ZC9s19845rkfiT4Et/HOhT2ssKTOY2TY4+WVCMMh+v86/PsizSWWYlS+y9H5p7n0GJoRxF"
    "Pke+69TxjSNXtNf0y21HT5luLO4jEkUi9GUj9Pp2r54+N3iC8+InxO034dW9yum6ck0f2maU4EkjKHH1wpAUd2P0rA+IV142/Z5n"
    "ufDek6jLB4eu5Wls7h4g0kf9+MMw+Vh3x9RjJrxe81S+1HUH1C6vJ7m/dg5uZZC0hYdDuJzkYFfsGQcMqnWlj6dRSi0/ZvdpvZtb"
    "XX5nzOPzO8VQlFp/a/yXqfoV4e0Cy8LaLZ6Tp0QhsrWMRxoOvuT6knJJ9TWh1r5v8M/tY21h4Oij1mxuL7XoQI8w4VJwBw7Mfun1"
    "wDzyOvDfBf7WUl54keLxJYQWekTELHNahma3Pq+T849SACPQ18TW4VziUqtWdO/K3rfWXmu57VPNcGlGKla/4ep9b+EvGs/hyTyp"
    "AZ7FjkxZ5T3X/CvWNM1m01q286znWZO4H3lPoR2r58sr+21Oziu7OeO6tZlDxzRMGVh6girtle3GnzrNbTPBKOjIcGvhq1BOTUtG"
    "j2NHqj6AIDDDDKnsa/N79oK41j4B/HPxPb6GkEOna2yanFFJFlCr7icAEYxJ5g47AV9oab8U7y3ULe26XYHG9Dsb8e38q8V/aqs7"
    "rxpP4Q8VeE9OluvEOh3RElu4UeZCcMM88gMuMDn94a+14LzGplWY+87Rmmt7K+69NdPmeJmuF+sUNFqn/wAOfL0n7RPi+cbIorBG"
    "PTy7dif1Y0ia38VvHf7u1TV5In4zZ2xgQfV1A/U19CfCn4qXfirxJqWga/ocfh/W7WJZ0hBOXXjPBHBwykcnIJ9K9T6mv0TM+O8b"
    "g6nsJUEpWv8AFdWezVlr9542HyWlXjzqpdelvzPkrwt+yp4o1q7WfxDeQ6TA53SZf7RcH8Adv4lvwr7n+C37PPgD4W2FtqPh7T/t"
    "moyxg/2tfkS3HI5CnGI+4IUD3zXHgbjiu9+GXiH7PK2kzt8khLwE9m7r+PX8/Wvy/OOI8zzWm41Klo9o6L/N/Nnv4bLsNhXeEbvu"
    "z0pnwCScAc818i/tO/tm2vhyG68L+AbuO81dgY7nWYWDRWvYrEejP/tdF9z07T9uiXVbb4Ez3Gl39xZRx38K3gt3KedA4ZCjY6qW"
    "ZOO+K/NgCvpOCuGcLj6azHFPmSdlHpddX39Dyc3zGpQfsKatdb/5D55pbueSeeRpppGLvJIxZmY8kknqSaixzS19MfDf9hjxP49+"
    "HaeIbjU4dBv7rEljp17Ax8yLHDyMDmPd1A2njnvX7RjsyweV01PFTUE3ZHyVDD1cTJqkrs+aY43lkSONS8jkKqqMkk9ABX6W/Cfw"
    "UvwL+CumeH2VU8Q6kpvNQI+8kjgZH/AVCoPdSa8W/Z//AGVNV+HPj6fxJ8Q7OGO00Uh9OgjmWVb25PKOMfwpjPIBzt44NeyeMPFc"
    "dpb6jrurTiO3gjaaV+yIo6AfoB3r8h4xzuGZTp4DBS5o6Nta3b2Xy/M+vyfAvDqWIrKz8+x80/tg+MwsekeF4JMsT9tuVB6DlYwf"
    "/Hzj2FfMoG1APxrb8aeLLnxz4r1LW7vPm3cpcJnIROiqPooA/CsVjz61+hZfglleApYP7SV5er3PncVX+tYiVXpsvQb70E4pC/NJ"
    "+orrOUUnIp0X3xTAMHPanRn96pHrRfUY4v3pA2DRnPWkznFVcRIG3Dil5BqIHnNKX5pDRMDlcHnNe0fs5/tP6p+z++pWj6edd0K+"
    "IkNiZ/JMcwGBIjbWxkYBGOcD058UWTI9acr5PpXPXoUcXRlh8TDmg+hpTqTozVSm7NH1lD/wUM8VXPjDTrmfQ9PsvDKTf6TZQhpL"
    "iSM8H96xA3DORhRkjnivujwz4m0zxn4fsdb0a7S+0y9iEsE8fRlPr6EHIIPIIINfjQRvXB5Fe7/st/tM3fwP1kaRq7y3fg6+kzNE"
    "vzNaOePOjH/oSjqORyOfhM+4Tw2JwqqZZTUakPsr7S/zPcwOaThU5cTK6fXt/wAA+4fjf8GNN+Jnh68hmthK8i5dUGHDDpIh7OP1"
    "HHsfzS+JXw01b4Ya61jqEZktnJNteKuEmX+jDuvb6YJ/XXR9WsfEOl2up6bdRXthdRiWC4gbckiHoQRXCfFf4MaN8StIube5tIpW"
    "lGWjfgO3Zgf4X9CK+O4a4nrZLV+r4i7pt6rqn5HtY/L4Y2HNHSXRn5L4zzSOe1eufGH9nPXvhleXM9tDNqOjxklpNn763H/TRR2/"
    "2hx9K8jHOc8V/ROExtDH0lWw0lJP+tT4CtQqYefJUVmfoH8OtBXwt4E0PSxgNBapvx3cjc5/76Jq94g8VaT4Us47rWNRh0+CSQRJ"
    "JM2AWPYV8ZeAPjp4o8AKlvFcjUtNXgWV7llQeiN1X6A49qyPiZ8S9T+J2vHUL0eRbxjZb2aMSkK9/qT3Pf6ACvyP/UnFV8wlLEzX"
    "s223Jb69Ld/wPr/7coww6VOPvLSzPuvS9b0/XIPO06+ttQg/56W0qyL+YJq4elfnn4L1+Xwx4r0nU45XiFtdRSSbGI3IHBYH1BGR"
    "iv0KzuAPYjIr5XiLIP7DqQUZ80Z3tpbY9TLsw+vRk3GzR4h8dYJvBnjfwp4/tUPlWsos78IOWjOcfmpkGf8AdrlPib+0zrun+KNS"
    "03w5JYrpsDiOK78nzJHO0bjkkr97OOOle++OfC0XjbwlqeiTMEF3EVRyM7HHKt+DAGvhbxb4O1XwLrEmmaxatbzryrdUlXsyN3H+"
    "etfZ8LU8Bm9OMcZFSqUk0k+sb3T+WqPGzWWIwjcqDajLVtd9vxLniD4meK/FBYanrt7cRt1hWQpH/wB8Lhf0r3b4SftS2eh+GEtf"
    "FEt02paeF+y3MEe951H3QecBxjqSMjHfOfmXr3pelfoWOyLAY+gsPUppRTuuWyt/w585Qx9fDzdSMrt99T6B+PH7YWufGHQ5/Ddn"
    "psGjeH5yhnVsSz3BVgwyxGEG5QcLzx94ivn3FLSFq7sBl+GyyisPhYcsf17s5q9epiZ89R3Z6N+zve+GtP8AjP4Xl8W2yXOim6CM"
    "JT+7SUgiJ3HQqHKkg8Y65HB/VnV9XttHs2urlwiDoB1Y+gFflL8IfgxqfxR1JZHD2WhRPie+K9fVI89W/Qd+wP3XLeXM9tawT3Mt"
    "wltEsMZlfc21QACT3Jxye5r8W4/dCvjKShUvKKalHou3zfU+0yGFSNKTlGyez7mh4i8RXHiO9M0vyRrxHEDwg/x96+Rv2rPiwt7M"
    "PBmmTbooWEmoyIeGccrF+HU++B2NelfHz4zw/DbRTYafKj+IrxP3Sdfs6HjzWH/oIPU+wNfFEssl1PJPM7SyyMXZ3OWZickk+tdX"
    "CGRWazPFR91fAu77+i6CzjHpL6rSer3/AMhq/ux0pOtDdelJnAr9PlPmbkz5FIRhR2pTz3pCeKyKAce9Kh/er9aYOp5p8S/vF+tC"
    "3ARuOlAfHUUp4pp4HHNMBQc0YpMGl6jpzT06AOztFKD07VHj86cp9aAJlc9KfgOuDUSsAaeuB060k2ndB5Htf7O37T2u/AnUlsrj"
    "zNW8JzvmfTi3MRPWSEn7req9G74OCP0n8E+NdI+Inhaw8RaHcG60u9QvFIyFDwSrAg9CCCD7ivxsmJZQM8V+w3wr0PTPDnw18M6Z"
    "o08V1plvp8KQXEJBWYbATICOu4kt+NflfHeDwtOnSxkIWqzbTa2aXV+Z9TktapJypSd4o1da8N2OvwbLuIFgMLKvDr+P9DXyv8Y/"
    "2JdP16WfUdDH9nXbZYvaR5jc/wC3F2Pun1INfXZOKFGRX5rl2b4vLKntMNNpn0NbD0sRHlqxuj8jvG3wO8YeBJJTd6VJd2cZ5vLI"
    "GWPHqcDcv/AgK4LcR1Ffs5qXh3TtWybm1R3P/LQfK35jmvKvGv7LHgzxlJJJc6dbvK/JkeLbIf8AtohVvzzX61l/iHFpRx1P5r/L"
    "/gnzNfIU3ehK3k/8z8ts5YV9/wDw11g698PvDt6z75JLGISOe7hQrfqDWP4k/wCCf+lzRzPpN5dW8+0mNFuVaMtjgEOmev8AtVy3"
    "hnwT8ffhr4ctNEtvANlqNnabwkv2qJ3ILFuSs/qT2rbPswwPEuFgsHVSnB7Sajo15jwFGtltSXtYtprpqezDrWN4q8IaR410xrDW"
    "LGO9tzyu4YaM+qsOVP0ryhPiB8Z5SVTwBYowOPnfA/8ARopWvvjtq+AumaHogP8AGXVsfhvf+VfF0snxGGmqixFODXXnX6antyxd"
    "OouX2cnf+6cl43/ZSn0+3ubzw7qhuUjVpBZXafvCAM7VdeCewyB9a+fEbNfWS/B74g+KRjxV8Q5YoT9+20lCqsPTICD/AMdNb/hf"
    "9nTwV4WkSX7A+rXCnIl1J/M5/wBwAL+YNfoOD4rp5fRcMbX9tPpyr827XPn62UvETTow5F1u/wBNT42awu0slvDazizZ/KFyYz5Z"
    "fGdu7GM8Hj2r6H+Fv7Kz3H2bVfF8qiBgJE0y3kBLjqPMccAey/mK9u8a+DLDxp4RvNCuI1ihljxCyKB5LjlGA9jjj0yO9cB8CfiQ"
    "+nWGo+D/ABZcR2Gp+HgVE1zIEV7deB8x4+XjB7qV965MZxNjM0y+c8AuSUX7yWsuV7NP10ehrRyuhhcRFV/eTWna/n+h7PY2Ftpl"
    "nDaWcEdrawqEjhhUKiD0AHSvMfjR8ddO+GllJZWjJfeIpV/d2wOVgz0eT0HovU+w5rz74t/tUJGs2l+Czvc5STVpF4H/AFyU9f8A"
    "eP4DvXzPdXU9/cy3N1M9xcSsXkllYszsepJPU1wZHwnOq1jM00juovd+vZfib4/N4wTo4XV9+i9CfWdZvvEOqXOpalcvd3tw5eSW"
    "Q5LH+gHQDtVIt2oz2pp61+nTnzWjFWS2R8ml1erYpPU03dQevtTcfWs/UBc5NKeBSdKUdc0gDBxToifNX60nali/1y/WhbgHXNNB"
    "55PFDCmjpgjNWBIVz3pM4NIG465oxj3qdgAn8aB0zSjp1oOAKdwEDU9XwfamHkdKM5WncCbcH4NerfBX9pbxj8EbhIdOuv7S0Etm"
    "XSL0loTk8lD1jb3Xg9wa8mXHenbgKyq06WJpuhiIKUH0ZcJzpy54OzP0v8KftxfDHX/D0moajqE3h++hTdLp11C8jk46RsgIfJ6d"
    "D6gV8teMP24fH+qfEOfW/Dt7/ZOiR/urbSJo1liaIHOZQernqSpGOgPHPzrsDAZFL047V8/g+GcowNSdSFPn5tLSs0l5f5noVcyx"
    "VaKi5Wt26n3V4A/4KK6VdRx2/jPw5PYz8BrzSGEsZPqY3IZR9GavfPCH7R3w18bqn9l+MNNEr9Le8l+yy59Asu0n8M1+TZAPbNNK"
    "AjjNebi+DMoxTcqXNSflqvuf+ZvSzfE09J2l+DP2rimjuIlkikSWNhlXRgQR9RTmICGvyQ+BXji98DfFXwndrqFxbacNTtxdRJMy"
    "RtE0gV9wBwRtJ61+tkn3STxmvy3iDh+WRVqcVU54zV07W2e3U+lwONWNjJ8tmj59lfMsnP8AEf50ynSKfMcgcbj/ADr4t+PPxF1m"
    "/wDiXrVnYa1fW+m2rrbrbwXLpHuVQH+UHGd26u7J8nqZzXlShPlUVdt6m2NxkcFTU5K99D7A1XxBpehRmTUtRtLBAM7rmdYx+prz"
    "fxN+014I0EMlveTazOP4LGLK593bC4+ma+MJN88jPLK0jtyWY5J/E0gRVx8vPvX6HhuDcBR1xFWU/JLlX6s+bq53XnpTgo/ifQUf"
    "7XmoS+J7aR9Hgt9AD4mhVi85U/xBuBkdcY9s9xsftG6V4S8VeGLPxbY6zZ2uoPCDDlsm+j7LtHO4dM446Njt8zMNwxURjx1ORX0F"
    "LJsFQr0sTg26Tho0teZdnc854+tOnKnWXPfv0HocjNKW4ppOBwKaeete3Vm6km2edFcqsKSPxpDzSt7UgNYlAKdxSY5ooEAGe9Ox"
    "SdutGTQAZFLHjzV+tJ1p0P8ArV+tCAYx96BjFM56U4ZqmAClA+U0nINOHSkA3JFAPT0pSM03GKAHZHPakJGPegDcOlG0CmAoal38"
    "00A0FSaVgJRKB3p28EVX6Gn8+lOwEgkHY0eZUYyKM0WAe53AetdzpXx4+I+h2qW1j421uK3jUKkTX0jqijgABicD2FcGSe1ICaco"
    "wqR5akVJeaTGpSi7xbXodfP8YPHVyjK/irU1DZzsuWQ/mMVyeSxZ3Yu7HJYnJJpo5FIPSlFQppxpQUU+ySG5SnrNt+o/cAaC+e2a"
    "bRn8qWhIpNNySaUikFAADk0uM0dKUDNJgJjFAFB60A0AGKX3opD14pAFKetNOQeKUGnYBc4ohIMy/WkbpRDxKO9OIhq1J3oopMsU"
    "9T9aVfuiiil0F0Beg+tNooo6h0FX/GlNFFJbgIPvfhR3P0ooo6jYh+9T1+6aKKsQN1ooopLZgIOppPWiimthIQ9BSDr+FFFLqNDj"
    "1pveiikxsce1NHT8aKKBDm708UUUwI/4z9aP4zRRQugwNKeooooQhG6UdqKKQDv8KaPvfhRRSW4H/9k="
)


def create_app_icon():
    """Load a user-provided icon, or fall back to the embedded artwork."""
    if os.path.lexists(APP_ICON_PATH):
        pixmap = QPixmap(APP_ICON_PATH)
        if not pixmap.isNull():
            return QIcon(pixmap)
        warnings.warn(
            f"Could not load application icon from {APP_ICON_PATH}; using the embedded icon instead",
            RuntimeWarning,
            stacklevel=2,
        )
    pixmap = QPixmap()
    if not pixmap.loadFromData(base64.b64decode(_APP_ICON_DATA), "JPEG"):
        raise RuntimeError("Could not decode the embedded Umbriel application icon")
    return QIcon(pixmap)


def desktop_entry_quote(value):
    """Quote one executable path according to the desktop-entry Exec syntax."""
    value = value.replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return f'"{value}"'


def install_desktop_icon(icon):
    """Install a matching per-user desktop entry for Wayland taskbar icon lookup."""
    if sys.platform != "linux":
        return
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    icon_directory = os.path.join(data_home, "icons", "hicolor", "128x128", "apps")
    application_directory = os.path.join(data_home, "applications")
    icon_path = os.path.join(icon_directory, "umbriel-settings.png")
    desktop_path = os.path.join(application_directory, "umbriel-settings.desktop")
    os.makedirs(icon_directory, exist_ok=True)
    os.makedirs(application_directory, exist_ok=True)
    if not icon.pixmap(128, 128).save(icon_path, "PNG"):
        raise OSError(f"Could not write application icon to {icon_path}")
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        # Inside an AppImage, sys.executable and the launcher live on a temporary mount.
        exec_line = desktop_entry_quote(appimage_path)
    else:
        exec_line = f"{desktop_entry_quote(sys.executable)} {desktop_entry_quote(LAUNCHER_PATH)}"
    desktop_entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Configure the Umbriel desktop environment\n"
        f"Exec={exec_line}\n"
        "Icon=umbriel-settings\n"
        "Terminal=false\n"
        "Categories=Settings;DesktopSettings;\n"
        "StartupNotify=true\n"
        "StartupWMClass=umbriel-settings\n"
    )
    write_text_file(desktop_path, desktop_entry)
    # The entry and icon from before the rename point at a launcher that no longer exists.
    for legacy in (os.path.join(application_directory, LEGACY_DIR_NAME + ".desktop"),
                   os.path.join(icon_directory, LEGACY_DIR_NAME + ".png")):
        with contextlib.suppress(FileNotFoundError):
            os.remove(legacy)
