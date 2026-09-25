"""Verdad de referencia de la muestra estratificada, etiquetada a mano
desde el nombre de archivo + la carpeta, ANTES de ejecutar el parser.

Clave = nombre de archivo. Valor = (serie_real, numero_real, tipo_real,
requiere_contexto).

`requiere_contexto=True` marca los casos donde la respuesta correcta NO
está en el nombre del archivo: abreviaturas que solo la carpeta resuelve
("Avras Cap Torrezno" → "Las Aventuras del Capitán Torrezno"), o el
autor delante de la obra, que es ambiguo por construcción. Sirven para
separar "el parser falla" de "esto es imposible de saber leyendo el
nombre" — el techo real del parsing por nombre.

tipo: grapa | tomo | pack | especial | obra_unica
"""

ETIQUETAS: dict[str, tuple[str, str, str, bool]] = {
    # ── A_singleton ──────────────────────────────────────────────────
    "Iberia Inc. - Integral 20 aniversario (Dolmen) [por capdiajo & redvirux] [CRG].cbr":
        ("Iberia Inc", "", "tomo", False),
    "Carta blanca (Jordi Lafebre).cbz":
        ("Carta blanca", "", "obra_unica", False),
    "El Regreso de Question (ECC - Spaceman Project) [Tildoras, CRGfunding].cbr":
        ("El Regreso de Question", "", "obra_unica", False),
    "La liga de los hombres extraordinarios -La Tempestad 02 por GBWilliams-Mastergel[Infinity-Gisicom].cbr":
        ("La liga de los hombres extraordinarios", "2", "grapa", False),
    "To Apeirón - Sequeiros [brut comix].cbr":
        ("To Apeirón", "", "obra_unica", False),
    "¿Me.estas.escuchando.-.Tillie.Walden.[jbabylon5][CRG].cbr":
        ("Me estas escuchando", "", "obra_unica", False),

    # ── B_pequena ────────────────────────────────────────────────────
    "_Avras Cap  Torrezno_Limbo sin fin_3_cilurnigo.cbz":
        ("Las Aventuras del Capitán Torrezno", "3", "tomo", True),
    "_Avras Cap  Torrezno_Limbo sin fin_3_cilurnigo(1).cbz":
        ("Las Aventuras del Capitán Torrezno", "3", "tomo", True),
    "El Don(Eurocomicss).cbr":
        ("El Don", "", "obra_unica", False),
    "Nancy in Hell Tomo 1(1).cbr":
        ("Nancy in Hell", "1", "tomo", False),
    "Nancy in Hell Tomo 1.cbr":
        ("Nancy in Hell", "1", "tomo", False),
    "EVENTOS - La Era de Ultrón.cbr":
        ("La Era de Ultrón", "", "obra_unica", False),
    "EVENTOS - La Era de Ultrón(1).cbr":
        ("La Era de Ultrón", "", "obra_unica", False),
    "Bribones - el corazon de un dios - por Jiman(CRG - FPJ).cbr":
        ("Bribones", "", "obra_unica", False),
    "Bribones - el corazon de un dios - por Jiman(CRG - FPJ)(1).cbr":
        ("Bribones", "", "obra_unica", False),
    "Caballero Luna Vol3 02 [por Carlos_1981][CRG](1).cbr":
        ("Caballero Luna", "2", "grapa", False),
    "Caballero Luna Vol3 02 [por Carlos_1981][CRG].cbr":
        ("Caballero Luna", "2", "grapa", False),
    "Caballero Luna Vol3 03 [por Carlos_1981][CRG].cbr":
        ("Caballero Luna", "3", "grapa", False),
    "Caballero Luna Vol3 03 [por Carlos_1981][CRG](1).cbr":
        ("Caballero Luna", "3", "grapa", False),
    "Caballero Luna Vol3 01 [por Carlos_1981][CRG].cbr":
        ("Caballero Luna", "1", "grapa", False),
    "Caballero Luna Vol3 01 [por Carlos_1981][CRG](1).cbr":
        ("Caballero Luna", "1", "grapa", False),
    "En un rayo de sol Vol.2 - Tillie Walden [xavib](1).cbr":
        ("En un rayo de sol", "2", "tomo", False),
    "En un rayo de sol Vol.2 - Tillie Walden [xavib].cbr":
        ("En un rayo de sol", "2", "tomo", False),
    "En un rayo de sol Vol.1 - Tillie Walden [xavib].cbr":
        ("En un rayo de sol", "1", "tomo", False),
    "En un rayo de sol Vol.1 - Tillie Walden [xavib](1).cbr":
        ("En un rayo de sol", "1", "tomo", False),
    "Bella muerte - Volumen 2 El oso (Astiberri) [por capdiajo y Tildoras] [CRG](1).cbr":
        ("Bella Muerte", "2", "tomo", False),
    "Bella muerte - Volumen 2 El oso (Astiberri) [por capdiajo y Tildoras] [CRG].cbr":
        ("Bella Muerte", "2", "tomo", False),
    "Bella Muerte - Volumen 1 (Astiberri) por Carlos_1981 [CRG].cbr":
        ("Bella Muerte", "1", "tomo", False),
    "Bella Muerte - Volumen 1 (Astiberri) por Carlos_1981 [CRG](1).cbr":
        ("Bella Muerte", "1", "tomo", False),
    "Arrowsmith (ECC) [Tildoras, CRG].cbr":
        ("Arrowsmith", "", "tomo", False),
    "Arrowsmith (ECC) [Tildoras, CRG](1).cbr":
        ("Arrowsmith", "", "tomo", False),
    "Estudio en Esmeralda [traducido por Gb, Letho y Vander][Infinity Cómics].cb7":
        ("Estudio en Esmeralda", "", "obra_unica", False),
    "Estudio en Esmeralda [traducido por Gb, Letho y Vander][Infinity Cómics](1).cb7":
        ("Estudio en Esmeralda", "", "obra_unica", False),
    "La Mala Pena 1 [por zaragway][CRG](1).cbr":
        ("La Mala Pena", "1", "tomo", False),
    "La Mala Pena 1 [por zaragway][CRG].cbr":
        ("La Mala Pena", "1", "tomo", False),
    "La Mala Pena 2 [por zaragway][CRG].cbr":
        ("La Mala Pena", "2", "tomo", False),
    "La Mala Pena 2 [por zaragway][CRG](1).cbr":
        ("La Mala Pena", "2", "tomo", False),
    "Los Inhumanos vol.3 por Jiman(CRG).cbr":
        ("Los Inhumanos", "3", "tomo", False),
    "Los Inhumanos vol.3 por Jiman(CRG)(1).cbr":
        ("Los Inhumanos", "3", "tomo", False),
    "El.Incal.(Integral).-.Jodorowsky.&.Moebius.[jbabylon5][16º.Aniversario.CRG].cbr":
        ("El Incal", "", "tomo", False),
    "El.Incal.(Integral).-.Jodorowsky.&.Moebius.[jbabylon5][16º.Aniversario.CRG](1).cbr":
        ("El Incal", "", "tomo", False),
    "El País Libre.- Un Relato de la Cruzada de los Niños (ECC) [Tildoras, CRG].cbr":
        ("El País Libre", "", "obra_unica", False),
    "The Fall (Planeta) [por capdiajo & redvirux] [CRG].cbr":
        ("The Fall", "", "obra_unica", False),
    "Taxus..La.Historia.completa.-.Isaac.Sanchez.[Umbriel.&.jbabylon5][CRG].cbr":
        ("Taxus", "", "tomo", False),
    "Horizontes Lejanos - Avtras cap Torrezno I Pin.cbr":
        ("Las Aventuras del Capitán Torrezno", "1", "tomo", True),
    "Horizontes Lejanos - Avtras cap Torrezno I Pin(1).cbr":
        ("Las Aventuras del Capitán Torrezno", "1", "tomo", True),
    "_Las aventuras del capitan Torrezno_Escala Real___S Valenzuela_cilurnigo.cbz":
        ("Las aventuras del capitan Torrezno", "", "tomo", False),
    "_Las aventuras del capitan Torrezno_Escala Real___S Valenzuela_cilurnigo(1).cbz":
        ("Las aventuras del capitan Torrezno", "", "tomo", False),
    "Daytripper (por Aruso) CRG 8º Aniversario.cbr":
        ("Daytripper", "", "obra_unica", False),
    "El.regreso.del.hombre.pez.-.Isaac.Sanchez.[jbabylon5][CRG].cbr":
        ("El regreso del hombre pez", "", "obra_unica", False),
    "Laura.Dean.me.ha.vuelto.a.dejar.-.Mariko.Tamaki.&.Rosemary.Valero-O´Connell.[jbabylon5][CRG].cbr":
        ("Laura Dean me ha vuelto a dejar", "", "obra_unica", False),

    # ── D_grande ─────────────────────────────────────────────────────
    "Death Note #082.howtoarsenio.blogspot.com.cbr": ("Death Note", "82", "grapa", False),
    "Death Note #065.howtoarsenio.blogspot.com.cbr": ("Death Note", "65", "grapa", False),
    "Death Note #084.howtoarsenio.blogspot.com.cbr": ("Death Note", "84", "grapa", False),
    "Death Note #068.howtoarsenio.blogspot.com.cbr": ("Death Note", "68", "grapa", False),
    "Death Note #074.howtoarsenio.blogspot.com.cbr": ("Death Note", "74", "grapa", False),
    "Death Note #058.howtoarsenio.blogspot.com.cbr": ("Death Note", "58", "grapa", False),
    "075.- Flash v2 067 - Er-Murazor &amp; Boo$Ter Gold.cbr": ("Flash", "67", "grapa", False),
    "256.- Flash v2 227 por Talphin y KeysersozeCRG.cbr": ("Flash", "227", "grapa", False),
    "068.- Flash v2 061 por Centigon y KeysersozeCRG.cbr": ("Flash", "61", "grapa", False),
    "048.- Flash v2 042.cbr": ("Flash", "42", "grapa", False),
    "076.- Flash v2 068 - Er-Murazor &amp; Boo&amp;Ter Gold.cbr": ("Flash", "68", "grapa", False),
    "224.- Flash v2 189 por Wild_CRG_.cbr": ("Flash", "189", "grapa", False),
    "JSA 81 (2006) (Lightray-DCP).cbr": ("JSA", "81", "grapa", False),
    "The Wicked + The Divine 030.cbr": ("The Wicked + The Divine", "30", "grapa", False),
    "The Wicked + The Divine 020.cbr": ("The Wicked + The Divine", "20", "grapa", False),
    "The Wicked + The Divine 037.cbr": ("The Wicked + The Divine", "37", "grapa", False),
    "Monstress #018 por Zur y Arsenio Lupín.cbr": ("Monstress", "18", "grapa", False),
    "Transmetropolitan - #20 - Ciudad Solitaria 2 de 4.howtoarsenio.blogspot.com.cbr":
        ("Transmetropolitan", "20", "grapa", False),
    "Transmetropolitan - #29 - Regreso a los Origenes 7 de 8.howtoarsenio.blogspot.com.cbr":
        ("Transmetropolitan", "29", "grapa", False),
    "Transmetropolitan - #42 - Sale el Sol 6 de 6.howtoarsenio.blogspot.com.cbr":
        ("Transmetropolitan", "42", "grapa", False),
    "Transmetropolitan - #06 - Mátame a Besos 2 de 2.howtoarsenio.blogspot.com.cbr":
        ("Transmetropolitan", "6", "grapa", False),
    "40 - Incorruptible #18.cbz": ("Incorruptible", "18", "grapa", False),
    "60 - Incorruptible #26.cbz": ("Incorruptible", "26", "grapa", False),
    # Dreadstar: el número real va DENTRO del paréntesis de la edición
    # anfitriona ("(02 Ed.Norma)", "(18 Ed.Forum)") o suelto antes de
    # "USA". Está en el nombre, así que es alcanzable — es RF-06.
    "78 Jim Starlin's Dreadstar (Malibu Comics)(02 Ed.Norma) [por Onslaught][CRG].cbr":
        ("Dreadstar", "2", "grapa", False),
    "74 Dreadstar (First Comics) 62 USA [Trad por Skullpirates y Howard el patero s.][8vo Aniv CRG].cbz":
        ("Dreadstar", "62", "grapa", False),
    "42 Dreadstar (First Comics) 30 USA [Traducido porke yo lo valgo][CRG].cbr":
        ("Dreadstar", "30", "grapa", False),
    "65 Dreadstar (First Comics) 53 USA [Trad por Skullpirates y Howard el patero s.][8vo Aniv CRG].cbz":
        ("Dreadstar", "53", "grapa", False),
    "30 Dreadstar (Epic Comics)(18 Ed.Forum) [por Andtorres3][CRG].cbr":
        ("Dreadstar", "18", "grapa", False),
    "11 Dreadstar Novela grafica (M.O. III) [Trad por Luindel y Howard el patero solitario][CRG].cbr":
        ("Dreadstar", "", "obra_unica", False),
    # Autor delante de la obra: ambiguo por construcción sin la carpeta.
    "Hiroaki Samura - La Espada del Inmortal 14 (Spanish, CRG) por Umbriel.cbr":
        ("La Espada del Inmortal", "14", "tomo", True),
}
