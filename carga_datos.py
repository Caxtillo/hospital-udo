# carga_datos.py
print("--- carga_datos.py: Script starting ---")
import sqlite3
import os
import random
import bcrypt
import traceback # Import traceback for detailed error printing
from datetime import datetime, timedelta
from faker import Faker
import json
print("--- carga_datos.py: Imports done ---")
# Importar funciones y constantes desde database.py
import database # <<< ASEGÚRATE QUE ESTO FUNCIONA (database.py en el mismo dir o PYTHONPATH)

# --- Configuración ---
SALT_ROUNDS = 12
NUM_PACIENTES = 10
NUM_CONSULTAS_MIN = 1
NUM_CONSULTAS_MAX = 3
NUM_EVOLUCIONES_MIN = 2
NUM_EVOLUCIONES_MAX = 8
PACIENTES_ABIERTOS = 4

# Inicializar Faker para datos ficticios
fake = Faker('es_ES')

# --- Funciones Auxiliares ---

def hash_password(password):
    """Genera un hash seguro de la contraseña y devuelve un string."""
    if not password:
        raise ValueError("La contraseña no puede estar vacía para hashear")
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=SALT_ROUNDS)
    hashed_pw_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_pw_bytes.decode('utf-8')

def generate_random_datetime(start_date, end_date):
    """Genera una fecha y hora aleatoria dentro de un rango."""
    # Asegurar que end_date es posterior a start_date
    if end_date <= start_date:
        end_date = start_date + timedelta(days=1) # Forzar al menos un día de diferencia
        
    time_between_dates = end_date - start_date
    seconds_between_dates = time_between_dates.total_seconds()
    # Manejar caso donde las fechas son muy cercanas
    if seconds_between_dates <= 1:
        return start_date 
    random_number_of_seconds = random.randrange(int(seconds_between_dates))
    return start_date + timedelta(seconds=random_number_of_seconds)

def generate_medical_text(num_sentences=3):
    """Genera texto médico ficticio corto."""
    return fake.paragraph(nb_sentences=num_sentences)

# --- Funciones de Creación de Datos ---

def crear_usuarios(conn, cursor):
    """Crea usuarios de ejemplo. Usa database.encrypt_data y database.log_action."""
    usuarios_creados = []
    admin_user_id = None
    print("Creando/Verificando usuarios...")
    users_data = [
        ('admin', 'adminpass', 'Admin Principal', 'administrador', 'V-11111111', '111', 'General'),
        ('dr_gomez', 'drgomezpass', 'Dr. Carlos Gómez', 'medico', 'V-22222222', '222', 'Gastroenterología'),
        ('dr_perez', 'drperezpass', 'Dra. Ana Pérez', 'medico', 'V-33333333', '333', 'Cardiología'),
        ('enf_lopez', 'enflopezpass', 'Enf. Luisa López', 'enfermeria', 'V-44444444', None, None),
        ('otro_user', 'otropass', 'Usuario Otro', 'otro', 'V-55555555', None, None),
    ]
    
    existing_users_count = 0
    newly_created_count = 0

    for i, (user, pwd, nombre, rol, cedula, mpps, especialidad) in enumerate(users_data):
        try:
            # Verificar si el usuario ya existe
            cursor.execute("SELECT id, rol FROM Usuarios WHERE nombre_usuario = ?", (user,))
            existing_user = cursor.fetchone()

            if existing_user:
                print(f"  Usuario '{user}' ya existe (ID: {existing_user[0]}). Saltando creación.")
                usuarios_creados.append({'id': existing_user[0], 'rol': existing_user[1]})
                if existing_user[1] == 'administrador':
                    admin_user_id = existing_user[0]
                existing_users_count += 1
                continue # Saltar al siguiente usuario

            # Si no existe, crearlo
            hashed_pwd = hash_password(pwd)
            nombre_enc = database.encrypt_data(nombre)
            cedula_enc = database.encrypt_data(cedula) # Encriptar cédula

            cursor.execute("""
                INSERT INTO Usuarios (nombre_usuario, hash_contrasena, nombre_completo, rol, cedula, mpps, especialidad)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user, hashed_pwd, nombre_enc, rol, cedula_enc, mpps, especialidad))
            
            user_id = cursor.lastrowid
            usuarios_creados.append({'id': user_id, 'rol': rol})
            if rol == 'administrador':
                admin_user_id = user_id
            print(f"  Usuario NUEVO creado: {user} (ID: {user_id})")
            newly_created_count += 1

            # Log de creación (solo para los nuevos)
            if admin_user_id: # Loguear como admin si es posible
                database.log_action(conn, admin_user_id, 'CREAR_USUARIO', f"Usuario '{user}' creado.", 'Usuarios', user_id)
            else: # Si el admin aún no se ha creado, loguear como el propio usuario (menos ideal)
                 database.log_action(conn, user_id, 'CREAR_USUARIO', f"Usuario '{user}' creado por sí mismo (carga inicial).", 'Usuarios', user_id)

        except sqlite3.IntegrityError as e:
            print(f"WARN: Error de integridad no esperado al procesar usuario '{user}': {e}")
        except Exception as e:
            print(f"ERROR procesando usuario '{user}': {e}")
            raise # Re-lanzar si es un error inesperado

    print(f"Proceso de usuarios finalizado. {newly_created_count} creados, {existing_users_count} ya existían.")
    
    # Asegurar que admin_user_id tenga un valor si existe un admin
    if not admin_user_id:
        admin_data = next((u for u in usuarios_creados if u['rol'] == 'administrador'), None)
        if admin_data:
            admin_user_id = admin_data['id']
        elif usuarios_creados: # Si no hay admin, usar el primer usuario para logs posteriores
             admin_user_id = usuarios_creados[0]['id']
             print(f"WARN: No se encontró/creó usuario admin. Usando ID {admin_user_id} para logs posteriores.")
        else:
            print("ERROR CRÍTICO: No hay usuarios disponibles.")
            
    return usuarios_creados, admin_user_id


def crear_pacientes(conn, cursor, num_pacientes, usuarios, admin_user_id):
    """Crea pacientes de ejemplo. Usa database.encrypt_data y database.log_action."""
    pacientes_creados = []
    print(f"Creando {num_pacientes} pacientes...")
    if not usuarios:
        print("ERROR: No hay usuarios disponibles para asignar como registradores.")
        return [], admin_user_id # Devolver admin_user_id aunque no se creen pacientes

    # Usar el admin_user_id recibido o el primer usuario como fallback
    registrador_log_id = admin_user_id or (usuarios[0]['id'] if usuarios else 1)

    for i in range(num_pacientes):
        numero_historia = f"HC-{random.randint(10000, 99999):05d}"
        # Generar cédula única (Faker se encarga de unique)
        while True:
            try:
                 cedula_num = fake.unique.random_number(digits=random.randint(7, 8), fix_len=False)
                 cedula_str = f"{random.choice(['V', 'E'])}-{cedula_num}"
                 # Verificar si ya existe (aunque unique debería prevenirlo, por si acaso)
                 cursor.execute("SELECT 1 FROM Pacientes WHERE cedula = ?", (database.encrypt_data(cedula_str),))
                 if cursor.fetchone() is None:
                     break # Cédula válida y no existe
            except OverflowError: # Faker a veces puede agotar las combinaciones únicas
                 print("WARN: Faker agotó cédulas únicas, generando aleatoria simple.")
                 cedula_str = f"{random.choice(['V', 'E'])}-{random.randint(1000000, 30000000)}"
                 # No se puede garantizar unicidad aquí sin más checks
                 break 
            except Exception as e_ced:
                 print(f"WARN: Error generando cédula única: {e_ced}. Usando aleatoria simple.")
                 cedula_str = f"{random.choice(['V', 'E'])}-{random.randint(1000000, 30000000)}"
                 break

        nombres = fake.first_name()
        apellidos = fake.last_name()
        sexo = random.choice(['Femenino', 'Masculino']) # Simplificado
        fecha_nac = fake.date_of_birth(minimum_age=5, maximum_age=95)
        usuario_registro = random.choice(usuarios)

        # Datos encriptados (usando database.encrypt_data)
        cedula_enc = database.encrypt_data(cedula_str)
        nombres_enc = database.encrypt_data(nombres)
        apellidos_enc = database.encrypt_data(apellidos)
        lugar_nac_enc = database.encrypt_data(fake.city())
        estado_civil_enc = database.encrypt_data(random.choice(['Soltero/a', 'Casado/a', 'Divorciado/a', 'Viudo/a', 'Concubino/a']))
        tel_hab_enc = database.encrypt_data(fake.phone_number())
        tel_mov_enc = database.encrypt_data(fake.phone_number())
        email_enc = database.encrypt_data(fake.email())
        direccion_enc = database.encrypt_data(fake.address().replace('\n', ', '))
        profesion_enc = database.encrypt_data(fake.job())
        emerg_nombre_enc = database.encrypt_data(fake.name()) # Añadir nombre contacto emergencia
        emerg_tel_enc = database.encrypt_data(fake.phone_number())
        emerg_parent_enc = database.encrypt_data(random.choice(['Hijo/a', 'Padre', 'Madre', 'Hermano/a', 'Cónyuge', 'Vecino/a', 'Otro']))
        emerg_dir_enc = database.encrypt_data(fake.address().replace('\n', ', '))
        notas_enc = database.encrypt_data(generate_medical_text(1)) if random.random() > 0.6 else None
        ap_asma = random.choice([0,1])
        ap_hta = random.choice([0,1])
        ap_dm = random.choice([0,1])
        ap_cardiopatia = random.choice([0,1])
        ap_otros = random.choice([0,1])
        ap_alergias_enc = database.encrypt_data(random.choice(['Penicilina', 'AINEs', 'Dipirona', 'Yodo', 'Látex', 'Ninguna Conocida'])) if random.random() > 0.2 else database.encrypt_data("Niega conocidas")
        ap_quirurgicos_enc = database.encrypt_data(random.choice(['Apendicectomia', 'Cesárea', 'Colecistectomia', 'Hernioplastia inguinal', 'Ninguno'])) if random.random() > 0.4 else None
        af_madre_enc = database.encrypt_data(random.choice(['Sana', 'HTA', 'DM', 'Cáncer Mama', 'ACV']))
        af_padre_enc = database.encrypt_data(random.choice(['Sano', 'HTA', 'Cardiopatía', 'DM', 'Cáncer Próstata', 'Desconocido']))
        af_hermanos_enc = database.encrypt_data(f"{random.randint(0,5)} hermanos, {random.choice(['aparentemente sanos', 'uno con DM', 'uno con HTA', 'sin datos'])}")
        af_hijos_enc = database.encrypt_data(f"{random.randint(0,4)} hijos, {random.choice(['sanos', 'uno con asma', 'sin datos'])}")
        hab_tabaco_enc = database.encrypt_data(random.choice(['Nunca', 'Ocasional social', 'Ex-fumador (dejó hace >1 año)', 'Activo leve (<5/día)', 'Activo mod (5-15/día)', 'Activo severo (>15/día)']))
        hab_alcohol_enc = database.encrypt_data(random.choice(['Nunca', 'Social ocasional', 'Social frecuente (fines de semana)', 'Diario leve', 'Diario moderado/severo', 'En Remisión']))
        hab_drogas_enc = database.encrypt_data(random.choice(['Nunca', 'Marihuana ocasional', 'Cocaína esporádica', 'Ex-consumidor', 'Polifármacos'])) if random.random() < 0.15 else database.encrypt_data("Niega")
        hab_cafe_enc = database.encrypt_data(random.choice(['No consume', '1-2 tazas/día', '3-5 tazas/día', '>5 tazas/día']))
        hab_perdida_peso_enc = database.encrypt_data(random.choice(['No', 'Sí, no intencionada', 'Sí, intencionada'])) if random.random() < 0.2 else database.encrypt_data("No")

        try:
            cursor.execute("""
                INSERT INTO Pacientes (
                    numero_historia, cedula, nombres, apellidos, sexo, fecha_nacimiento,
                    lugar_nacimiento, estado_civil, telefono_habitacion, telefono_movil, email,
                    direccion, profesion_oficio,
                    emerg_nombre, emerg_telefono, emerg_parentesco, emerg_direccion, -- emerg_nombre añadido
                    usuario_registro_id, notas_adicionales,
                    ap_asma, ap_hta, ap_dm, ap_cardiopatia, ap_otros, -- Booleanos añadidos
                    ap_alergias, ap_quirurgicos,
                    af_madre, af_padre, af_hermanos, af_hijos, -- Antecedentes familiares
                    hab_tabaco, hab_alcohol, hab_drogas, hab_cafe, hab_perdida_peso -- Hábitos añadidos
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero_historia, cedula_enc, nombres_enc, apellidos_enc, sexo, fecha_nac,
                lugar_nac_enc, estado_civil_enc, tel_hab_enc, tel_mov_enc, email_enc,
                direccion_enc, profesion_enc,
                emerg_nombre_enc, emerg_tel_enc, emerg_parent_enc, emerg_dir_enc, # emerg_nombre añadido
                usuario_registro['id'], notas_enc,
                ap_asma, ap_hta, ap_dm, ap_cardiopatia, ap_otros, # Booleanos añadidos
                ap_alergias_enc, ap_quirurgicos_enc,
                af_madre_enc, af_padre_enc, af_hermanos_enc, af_hijos_enc,
                hab_tabaco_enc, hab_alcohol_enc, hab_drogas_enc, hab_cafe_enc, hab_perdida_peso_enc # Hábitos añadidos
            ))
            paciente_id = cursor.lastrowid
            pacientes_creados.append({'id': paciente_id, 'numero_historia': numero_historia})
            print(f"  Paciente creado: {nombres} {apellidos} (ID: {paciente_id}, HC: {numero_historia})")

            # Log de creación de paciente
            database.log_action(conn, registrador_log_id, 'CREAR_PACIENTE', f"Paciente '{nombres} {apellidos}' (HC: {numero_historia}) creado.", 'Pacientes', paciente_id, detalles={'registrado_por': usuario_registro['id']})

        except sqlite3.IntegrityError as e:
             print(f"WARN: Error de integridad al crear paciente {nombres} {apellidos} (HC: {numero_historia}, Cedula: {cedula_str}) - {e}. Saltando...")
        except Exception as e:
            print(f"ERROR creando paciente {nombres} {apellidos}: {e}")
            traceback.print_exc() # Mostrar traceback para errores inesperados
            
    print(f"Pacientes creados: {len(pacientes_creados)}.")
    # Devolver el ID de admin usado para los logs
    return pacientes_creados, registrador_log_id


def crear_consultas_y_detalles(conn, cursor, pacientes, usuarios, admin_user_id):
    """Crea consultas y detalles. Usa database.encrypt/decrypt/log_action."""
    print("Creando consultas y detalles...")
    if not pacientes or not usuarios:
        print("ERROR: Faltan pacientes o usuarios para crear consultas.")
        return

    # Usar el admin_user_id recibido o el primer usuario como fallback para logs
    registrador_log_id = admin_user_id or (usuarios[0]['id'] if usuarios else 1)

    medicos = [u for u in usuarios if u['rol'] == 'medico']
    enfermeria = [u for u in usuarios if u['rol'] == 'enfermeria']
    if not medicos: medicos = usuarios # Fallback
    if not enfermeria: enfermeria = usuarios # Fallback

    pacientes_con_consulta_abierta = 0
    pacientes_procesados = 0

    for paciente in pacientes:
        paciente_id = paciente['id']
        num_consultas_paciente = random.randint(NUM_CONSULTAS_MIN, NUM_CONSULTAS_MAX)
        print(f"  Procesando Paciente ID: {paciente_id} ({paciente['numero_historia']}) - Creando {num_consultas_paciente} consulta(s)")

        ultima_fecha_egreso = datetime.now() - timedelta(days=random.randint(300, 730)) # Empezar más atrás

        for i in range(num_consultas_paciente):
            es_ultima_consulta = (i == num_consultas_paciente - 1)
            dejar_abierta = (pacientes_procesados < PACIENTES_ABIERTOS and es_ultima_consulta)

            fecha_ingreso = generate_random_datetime(ultima_fecha_egreso + timedelta(days=random.randint(5,30)), ultima_fecha_egreso + timedelta(days=random.randint(40, 120)))
            fecha_egreso = None
            usuario_cierre_id = None
            if not dejar_abierta:
                 dias_estancia = random.randint(0, 20) # Puede ser egreso el mismo día
                 fecha_egreso = fecha_ingreso + timedelta(days=dias_estancia, hours=random.randint(1,23))
                 ultima_fecha_egreso = fecha_egreso
                 usuario_cierre = random.choice(medicos)
                 usuario_cierre_id = usuario_cierre['id']
            # else: # Si queda abierta, no actualizar ultima_fecha_egreso

            usuario_ingreso = random.choice(medicos)
            
            # Datos encriptados (usando database.encrypt_data)
            motivo_consulta_enc = database.encrypt_data(random.choice(["Dolor abdominal", "Vómitos y diarrea", "Sangrado digestivo", "Control", "Estudio endoscópico programado", "Ictericia"]))
            hea_enc = database.encrypt_data(generate_medical_text(random.randint(4,8)))
            diag_ingreso_enc = database.encrypt_data(random.choice(["Gastritis Crónica", "Colelitiasis", "Hemorragia Digestiva Superior", "Reflujo Gastroesofágico", "Síndrome Diarreico Agudo", "Pancreatitis Leve"]))

            try:
                cursor.execute("""
                    INSERT INTO Consultas (
                        paciente_id, usuario_id, fecha_hora_ingreso, fecha_hora_egreso, usuario_cierre_id,
                        motivo_consulta, historia_enfermedad_actual, diagnostico_ingreso,
                        fecha_ultima_mod, usuario_ultima_mod_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    paciente_id, usuario_ingreso['id'], fecha_ingreso, fecha_egreso, usuario_cierre_id,
                    motivo_consulta_enc, hea_enc, diag_ingreso_enc,
                    fecha_ingreso, usuario_ingreso['id']
                ))
                consulta_id = cursor.lastrowid
                status = "ABIERTA" if dejar_abierta else "CERRADA"
                print(f"    Consulta creada ID: {consulta_id} ({status}) - Ingreso: {fecha_ingreso.strftime('%Y-%m-%d %H:%M')}")

                # Log de creación de consulta (usando database.log_action)
                database.log_action(conn, registrador_log_id, 'CREAR_CONSULTA', f"Consulta para paciente ID {paciente_id} creada (Status: {status}).", 'Consultas', consulta_id, detalles={'paciente_id': paciente_id, 'usuario_ingreso_id': usuario_ingreso['id'], 'fecha_ingreso': fecha_ingreso.isoformat()})

                poblar_detalles_consulta(conn, cursor, consulta_id, paciente_id, fecha_ingreso, fecha_egreso, usuarios, medicos, enfermeria, registrador_log_id, hea_enc, diag_ingreso_enc) # Pasar HEA y Dx

                if dejar_abierta:
                    pacientes_con_consulta_abierta += 1
            
            except Exception as e:
                print(f"ERROR creando consulta para paciente {paciente_id}: {e}")
                traceback.print_exc()

        pacientes_procesados += 1

    print(f"Consultas y detalles creados. Consultas abiertas dejadas: {pacientes_con_consulta_abierta}")


def poblar_detalles_consulta(conn, cursor, consulta_id, paciente_id, fecha_ingreso, fecha_egreso, usuarios, medicos, enfermeria, admin_user_id, hea_enc_consulta, diag_ingreso_enc_consulta):
    print(f"      Poblando detalles para Consulta ID: {consulta_id} (Paciente ID: {paciente_id})")
    fecha_fin_periodo = fecha_egreso if fecha_egreso else datetime.now()

    # --- Examen Físico ---
    # ... (tu código de examen físico, parece estar bien) ...
    try:
        ef_fecha = generate_random_datetime(fecha_ingreso, fecha_ingreso + timedelta(hours=2))
        usuario_ef = random.choice(medicos + enfermeria)
        ta_enc = database.encrypt_data(f"{random.randint(90, 180)}/{random.randint(50, 110)}")
        temp_enc = database.encrypt_data(f"{random.uniform(36.0, 39.0):.1f}")
        piel_enc = database.encrypt_data(random.choice(["Normohidratada, normocoloreada, tibia", "Palidez cutáneo-mucosa moderada", "Ictericia leve en escleras", "Térmica, diaforética"]))
        resp_enc = database.encrypt_data(random.choice(["Murmullo vesicular audible en ambos campos pulmonares, sin agregados.", "Roncus dispersos en bases pulmonares.", "Hipoventilación en base pulmonar derecha, matidez a la percusión."]))
        cv_enc = database.encrypt_data(random.choice(["Ruidos cardíacos rítmicos, normofonéticos, sin soplos.", "Taquicardia sinusal, no se auscultan soplos.", "Ruidos cardíacos apagados, soplo sistólico II/VI en foco mitral."]))
        abd_enc = database.encrypt_data(random.choice(["Blando, depresible, no doloroso a la palpación superficial ni profunda, RHA presentes.", "Dolor a la palpación en epigastrio y mesogastrio, sin signos de irritación peritoneal.", "Distendido, timpánico, RHA aumentados en frecuencia y tono.", "Defensa voluntaria en fosa ilíaca derecha, Blumberg dudoso."]))
        neuro_enc = database.encrypt_data(random.choice(["Vigil, consciente, orientado en tiempo, espacio y persona. Glasgow 15/15.", "Somnoliento, despierta al llamado, responde coherentemente. Pares craneales conservados.", "Confuso, desorientado. No signos de focalización."]))
        extrem_enc = database.encrypt_data(random.choice(["Simétricas, eutróficas, móviles, pulsos periféricos presentes y simétricos.", "Edema ++ en miembros inferiores hasta rodillas, fóvea presente.", "Llenado capilar < 2 segundos en todos los lechos ungueales."]))
        otros_hallazgos_ef_enc = database.encrypt_data(fake.sentence(nb_words=random.randint(5,15))) if random.random() < 0.3 else None
        cursor.execute("""
            INSERT INTO ExamenesFisicos (consulta_id, fecha_hora, ef_ta, ef_fr, ef_fc, ef_sato2, ef_temp, ef_piel, ef_respiratorio, ef_cardiovascular, ef_abdomen, ef_neurologico, ef_extremidades, ef_otros_hallazgos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (consulta_id, ef_fecha, ta_enc, random.randint(12, 28), random.randint(50, 120), random.randint(88, 100), temp_enc, piel_enc, resp_enc, cv_enc, abd_enc, neuro_enc, extrem_enc, otros_hallazgos_ef_enc))
        ef_id = cursor.lastrowid
        database.log_action(conn, admin_user_id, 'CREAR_EXAMEN_FISICO', f"Examen físico para consulta {consulta_id}", 'ExamenesFisicos', ef_id)
    except sqlite3.IntegrityError: print(f"WARN: EF para consulta {consulta_id} ya existe.")
    except Exception as e: print(f"ERROR creando EF para consulta {consulta_id}: {e}"); traceback.print_exc()


    # --- Evoluciones ---
    # ... (tu código de evoluciones, parece estar bien) ...
    num_evoluciones = random.randint(NUM_EVOLUCIONES_MIN, NUM_EVOLUCIONES_MAX)
    evoluciones_creadas_ids = []
    last_ev_fecha = fecha_ingreso
    for _ in range(num_evoluciones):
        ev_fecha = generate_random_datetime(last_ev_fecha + timedelta(hours=1), fecha_fin_periodo - timedelta(hours=1) if fecha_fin_periodo > last_ev_fecha + timedelta(hours=2) else last_ev_fecha + timedelta(hours=2) )
        if ev_fecha > fecha_fin_periodo : ev_fecha = fecha_fin_periodo
        last_ev_fecha = ev_fecha
        usuario_ev = random.choice(medicos + enfermeria)
        dias_hosp = max(0,(ev_fecha.date() - fecha_ingreso.date()).days)
        subj_enc = database.encrypt_data(f"Paciente refiere {random.choice(['mejoría progresiva', 'persistencia de dolor leve', 'buena tolerancia oral', 'expectoración escasa', 'mareos ocasionales'])}.")
        obj_enc = database.encrypt_data(f"Al examen físico: {random.choice(['estable, afebril, hidratado', 'ligera palidez, eupneico', 'abdomen blando, sin dolor significativo', 'herida quirúrgica en buen estado', 'consciente, orientado'])}.")
        ta_ev_enc = database.encrypt_data(f"{random.randint(90,170)}/{random.randint(50,100)}")
        temp_ev_enc = database.encrypt_data(f"{random.uniform(36.1,38.0):.1f}")
        diag_ev_enc = database.encrypt_data(f"Impresión Diagnóstica: {generate_medical_text(random.randint(1,2))}")
        plan_ev_enc = database.encrypt_data(f"Plan: {random.choice(['Mantener conducta expectante.', 'Ajustar dosis de analgesia.', 'Solicitar control de laboratorio mañana.', 'Valorar alta médica en próximas 24h.', 'Discutir caso con especialista.'])}")
        com_ev_enc = database.encrypt_data(fake.sentence(nb_words=random.randint(8,20))) if random.random() < 0.4 else None
        try:
            cursor.execute("""
                INSERT INTO Evoluciones (consulta_id, usuario_id, fecha_hora, dias_hospitalizacion, ev_subjetivo, ev_objetivo, ev_ta, ev_fc, ev_fr, ev_sato2, ev_temp, ev_diagnosticos, ev_tratamiento_plan, ev_comentario, fecha_ultima_mod, usuario_ultima_mod_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (consulta_id, usuario_ev['id'], ev_fecha, dias_hosp, subj_enc, obj_enc, ta_ev_enc, random.randint(55,110), random.randint(14,26), random.randint(90,100), temp_ev_enc, diag_ev_enc, plan_ev_enc, com_ev_enc, ev_fecha, usuario_ev['id']))
            ev_id = cursor.lastrowid
            evoluciones_creadas_ids.append(ev_id)
            database.log_action(conn, admin_user_id, 'CREAR_EVOLUCION', f"Evolución para consulta {consulta_id}", 'Evoluciones', ev_id)
        except Exception as e: print(f"ERROR creando Evolución para consulta {consulta_id}: {e}"); traceback.print_exc()


    # --- Órdenes Médicas (usando JSON Blob) ---
    # ... (tu código de órdenes médicas, parece estar bien) ...
    num_ordenes = random.randint(1, 3)
    ordenes_creadas_ids = []
    for _ in range(num_ordenes):
        orden_fecha = generate_random_datetime(fecha_ingreso + timedelta(minutes=30), fecha_fin_periodo)
        usuario_orden = random.choice(medicos)
        evolucion_id_orden = random.choice(evoluciones_creadas_ids) if evoluciones_creadas_ids and random.random() > 0.5 else None
        orden_json_data = {"fecha_creacion_orden": orden_fecha.isoformat()}
        if random.random() < 0.8: orden_json_data["hospitalizacion"] = { "indicada": True, "lugar": random.choice(["Piso 2 - Hab 201", "UCI - Cama 5", "Emergencia - Observación"])}
        if random.random() < 0.9: tipo_dieta_actual = random.choice(["Absoluta", "Líquida", "Blanda"]); orden_json_data["dieta"] = {"tipo_inicial": tipo_dieta_actual}; # ... (más detalles dieta)
        if random.random() < 0.7: orden_json_data["hp"] = {"indicada": True, "soluciones": [], "observaciones_generales": "Vigilar sobrecarga." if random.random() < 0.3 else None}; # ... (añadir soluciones)
        if random.random() < 0.95: orden_json_data["medicamentos"] = {"indicada": True, "items": []}; # ... (añadir medicamentos)
        orden_json_blob_enc = database.encrypt_data(json.dumps(orden_json_data))
        estado_om = random.choice(['Pendiente', 'Realizada']) if fecha_egreso else 'Pendiente'
        try:
            cursor.execute("""INSERT INTO OrdenesMedicas (consulta_id, evolucion_id, usuario_id, fecha_hora, orden_json_blob, estado) VALUES (?, ?, ?, ?, ?, ?)""",
                           (consulta_id, evolucion_id_orden, usuario_orden['id'], orden_fecha, orden_json_blob_enc, estado_om))
            orden_id = cursor.lastrowid; ordenes_creadas_ids.append(orden_id)
            database.log_action(conn, admin_user_id, 'CREAR_ORDEN_MEDICA', f"Orden JSON para consulta {consulta_id}", 'OrdenesMedicas', orden_id)
        except Exception as e: print(f"ERROR creando Orden Médica JSON para consulta {consulta_id}: {e}"); traceback.print_exc()


    # --- Complementarios ---
    print(f"      Generando complementarios para Consulta ID: {consulta_id}")
    tipos_complementarios_a_crear = {
        'Laboratorio': random.randint(2, 4), # Generar más laboratorios
        'Imagen': random.randint(1, 3),      # Al menos una imagen
        'Patologia': random.randint(0, 2),
        'Endoscopia': random.randint(0, 1)
    }

    for tipo_comp, cantidad in tipos_complementarios_a_crear.items():
        for i in range(cantidad): # Asegurar que el bucle se ejecute 'cantidad' veces
            print(f"        Creando complementario tipo '{tipo_comp}', item {i+1}/{cantidad}")
            fecha_reg_comp = generate_random_datetime(fecha_ingreso + timedelta(hours=random.randint(1, 24*3)), fecha_fin_periodo) # Que el registro sea después del ingreso
            fecha_realiz_comp = generate_random_datetime(fecha_ingreso, fecha_reg_comp - timedelta(minutes=30) if fecha_reg_comp > fecha_ingreso + timedelta(minutes=31) else fecha_reg_comp)
            usuario_reg_comp = random.choice(medicos + enfermeria) # Usuario que registra
            
            nombre_estudio_plano = f"Estudio Genérico de {tipo_comp}" # Default
            if tipo_comp == 'Laboratorio':
                nombre_estudio_plano = random.choice([
                    'Hematología Completa con Plaquetas', 'Perfil Bioquímico (Glic, Urea, Creat, Ac. Úrico)', 
                    'Electrolitos Séricos (Na, K, Cl, Ca, Mg)', 'Perfil Hepático Completo (BT, BD, BI, TGO, TGP, FAL, GGT, Prot. Tot, Alb)', 
                    'Uroanálisis con Sedimento', 'Perfil Lipídico (Col, Trig, HDL, LDL)', 
                    'Tiempos de Coagulación (TP, TPT, INR)', 'Gasometría Arterial', 'VSG y PCR'
                ])
            elif tipo_comp == 'Imagen':
                nombre_estudio_plano = random.choice([
                    'Rayos X de Tórax (PA y Lateral)', 'Ecosonograma Abdominal Completo', 
                    'TAC de Cráneo Simple', 'TAC de Abdomen con Contraste IV', 'RM de Columna Lumbar', 
                    'Eco Doppler de Miembros Inferiores (Arterial y Venoso)'
                ])
            elif tipo_comp == 'Patologia':
                nombre_estudio_plano = random.choice([
                    'Biopsia Gástrica (Antro y Cuerpo) para H. pylori', 'Citología de Líquido Ascítico', 
                    'Estudio Histopatológico de Pólipo Colónico', 'PAAF de Nódulo Tiroideo'
                ])
            elif tipo_comp == 'Endoscopia':
                nombre_estudio_plano = random.choice([
                    'Gastroscopia (VEDA) Diagnóstica', 'Colonoscopia Total con Sedación', 
                    'Rectosigmoidoscopia Flexible', 'CPRE Terapéutica'
                ])
            
            posibles_estados = ['Solicitado', 'Muestra Tomada', 'En Proceso', 'Realizado Completo', 'Informado', 'Cancelado']
            estado_comp = random.choice(posibles_estados)

            resultado_texto_plano = None
            if estado_comp in ['Realizado Completo', 'Informado']:
                resultado_texto_plano = f"Informe para {nombre_estudio_plano}:\n{generate_medical_text(random.randint(4,10))}\n\nConclusión: {fake.bs()}."
            
            archivo_path_texto_plano = None
            if estado_comp == 'Informado' and random.random() < 0.7: 
                 archivo_path_texto_plano = f"/uploads/complementarios_test/{paciente_id}/informe_{tipo_comp.lower().replace(' ', '_')}_{fake.uuid4()[:6]}.pdf"

            nombre_estudio_enc = database.encrypt_data(nombre_estudio_plano)
            resultado_enc = database.encrypt_data(resultado_texto_plano) if resultado_texto_plano else None
            archivo_adjunto_path_enc = database.encrypt_data(archivo_path_texto_plano) if archivo_path_texto_plano else None
            
            orden_medica_id_para_comp = None
            if ordenes_creadas_ids and random.random() < 0.65: # 65% de probabilidad de enlazar
                orden_medica_id_para_comp = random.choice(ordenes_creadas_ids)
                print(f"          -> Enlazando a Orden ID: {orden_medica_id_para_comp}")


            try:
                cursor.execute("""
                    INSERT INTO Complementarios (
                        paciente_id, consulta_id, orden_medica_id, usuario_registrador_id, 
                        fecha_registro, tipo_complementario, nombre_estudio, fecha_realizacion, 
                        resultado_informe, archivo_adjunto_path, estado,
                        fecha_ultima_mod, usuario_ultima_mod_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (
                    paciente_id, consulta_id, orden_medica_id_para_comp, usuario_reg_comp['id'], 
                    fecha_reg_comp, tipo_comp, nombre_estudio_enc, fecha_realiz_comp, 
                    resultado_enc, archivo_adjunto_path_enc, estado_comp,
                    usuario_reg_comp['id'] # Quién lo creó es el primer "último modificador"
                ))
                comp_id = cursor.lastrowid
                print(f"        OK: Complementario ID {comp_id} ({tipo_comp} - {estado_comp}) creado.")
                database.log_action(conn, admin_user_id, 'CREAR_COMPLEMENTARIO', f"Complementario ID {comp_id} ({tipo_comp}) para consulta {consulta_id}", 'Complementarios', comp_id)
            except Exception as e:
                print(f"ERROR creando Complementario ({tipo_comp}) para consulta {consulta_id}: {e}")
                traceback.print_exc()

    # --- Recipes ---
    # ... (tu código de recipes) ...
    if fecha_egreso or (datetime.now() - fecha_ingreso).days < random.randint(3,10) :
        num_recipes = random.randint(0, 2)
        for _ in range(num_recipes):
            fecha_emision_recipe = generate_random_datetime(last_ev_fecha if evoluciones_creadas_ids else fecha_ingreso, fecha_fin_periodo)
            usuario_recipe = random.choice(medicos)
            evolucion_id_recipe = random.choice(evoluciones_creadas_ids) if evoluciones_creadas_ids and random.random() > 0.4 else None
            tipo_recipe = random.choice(['Alta', 'Tratamiento Ambulatorio', 'Continuación'])
            recipe_texto_items = [ f"{random.choice(['Amoxicilina', 'Ciprofloxacina', 'Losartan', 'Omeprazol', 'Metformina'])} {random.choice(['500mg', '250mg', '50mg', '20mg', '850mg'])} {random.choice(['VO', 'SL'])} {random.choice(['c/8h', 'c/12h', 'OD', 'BID'])} x {random.randint(5,14)} días.", f"{random.choice(['Paracetamol', 'Ibuprofeno', 'Ketoprofeno'])} {random.choice(['500mg', '1g', '400mg', '100mg'])} {random.choice(['VO', 'IM'])} {random.choice(['c/6h', 'SOS dolor', 'TID'])}.", "Reposo relativo." if random.random() < 0.5 else None, "Control por consulta externa en 1 semana." if tipo_recipe == 'Alta' else None ]
            recipe_texto = "\n".join(filter(None, recipe_texto_items))
            recipe_texto_enc = database.encrypt_data(recipe_texto)
            try:
                cursor.execute("""INSERT INTO Recipes (paciente_id, consulta_id, evolucion_id, usuario_id, fecha_emision, tipo, recipe_texto) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                               (paciente_id, consulta_id, evolucion_id_recipe, usuario_recipe['id'], fecha_emision_recipe, tipo_recipe, recipe_texto_enc))
                recipe_id = cursor.lastrowid
                database.log_action(conn, admin_user_id, 'CREAR_RECIPE', f"Recipe ({tipo_recipe}) para consulta {consulta_id}", 'Recipes', recipe_id)
            except Exception as e: print(f"ERROR creando Recipe para consulta {consulta_id}: {e}"); traceback.print_exc()

    # --- Informe Médico ---
    # ... (tu código de informes médicos) ...
    if fecha_egreso and random.random() < 0.6:
        fecha_inf = fecha_egreso + timedelta(hours=random.randint(1,5))
        usuario_inf = random.choice(medicos)
        tipo_inf = random.choice(['Alta Médica', 'Resumen de Historia', 'Informe para Seguro'])
        resumen_hea = database.decrypt_data(hea_enc_consulta)[:150] if hea_enc_consulta else "Motivo de consulta referido."
        resumen_diag_ing = database.decrypt_data(diag_ingreso_enc_consulta) if diag_ingreso_enc_consulta else "Diagnóstico al ingreso."
        resumen_evol_txt = "Paciente evolucionó satisfactoriamente."
        if evoluciones_creadas_ids:
            try:
                cursor.execute("SELECT ev_diagnosticos, ev_tratamiento_plan FROM Evoluciones WHERE id = ?",(random.choice(evoluciones_creadas_ids),))
                last_ev_data = cursor.fetchone();_ = database.decrypt_data(last_ev_data[0]) if last_ev_data and last_ev_data[0] else "No especificado";__ = database.decrypt_data(last_ev_data[1]) if last_ev_data and last_ev_data[1] else "Continuar indicaciones.";resumen_evol_txt = f"Durante su hospitalización, paciente cursó con {_}. Plan de tratamiento incluyó {__[:100]}..."
            except Exception as e_inf_ev: print(f"WARN: Error obteniendo datos de evolución para informe: {e_inf_ev}")
        paciente_nombre_completo_para_informe = "[Nombre Paciente]" # Idealmente, obtenerlo de la BD o pasarlo
        cursor.execute("SELECT nombres, apellidos FROM Pacientes WHERE id = ?", (paciente_id,))
        pac_nombres_row = cursor.fetchone()
        if pac_nombres_row:
            n_dec_inf = database.decrypt_data(pac_nombres_row[0])
            a_dec_inf = database.decrypt_data(pac_nombres_row[1])
            paciente_nombre_completo_para_informe = f"{n_dec_inf} {a_dec_inf}".strip()

        contenido_informe = f"INFORME MÉDICO - {tipo_inf.upper()}\n\nPaciente: {paciente_nombre_completo_para_informe}\nHC: {paciente.get('numero_historia', 'N/A')}\nFecha Ingreso: {fecha_ingreso.strftime('%d/%m/%Y %H:%M')}\nFecha Egreso: {fecha_egreso.strftime('%d/%m/%Y %H:%M')}\n\nRESUMEN DE INGRESO:\n{resumen_hea}...\n\nDIAGNÓSTICO DE INGRESO:\n{resumen_diag_ing}\n\nEVOLUCIÓN Y TRATAMIENTO:\n{resumen_evol_txt}\n\nCONDICIONES DE EGRESO:\nPaciente egresa en buenas condiciones generales.\n\nINDICACIONES AL ALTA:\n- Cumplir tratamiento según récipe.\n- Control por consulta externa en 1 semana.\n\nMédico Tratante: Dr(a). {database.decrypt_data(usuario_inf['nombre_completo']) if usuario_inf.get('nombre_completo') else usuario_inf['nombre_usuario']}\nMPPS: {usuario_inf.get('mpps', 'N/A')}"
        contenido_enc = database.encrypt_data(contenido_informe)
        try:
            cursor.execute("""INSERT INTO InformesMedicos (paciente_id, consulta_id, usuario_id, fecha_creacion, tipo_informe, contenido_texto) VALUES (?, ?, ?, ?, ?, ?)""",
                           (paciente_id, consulta_id, usuario_inf['id'], fecha_inf, tipo_inf, contenido_enc))
            informe_id = cursor.lastrowid
            database.log_action(conn, admin_user_id, 'CREAR_INFORME', f"Informe ({tipo_inf}) para consulta {consulta_id}", 'InformesMedicos', informe_id)
        except Exception as e: print(f"ERROR creando Informe Médico para consulta {consulta_id}: {e}"); traceback.print_exc()          
# --- Función Principal ---
def main():
    print("Inicializando base de datos (creando tablas si no existen)...")
    database.initialize_database() # CORRECTO
    print("-" * 30)

    conn = None
    try:
        conn = database.connect_db() # CORRECTO
        if not conn:
            print("ERROR CRÍTICO: No se pudo conectar a la base de datos.")
            return

        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM Pacientes")
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"ADVERTENCIA: Ya existen {count} pacientes en la base de datos.")
            respuesta = input("¿Desea continuar y añadir más datos? (s/N): ").strip().lower()
            if respuesta != 's':
                print("Operación cancelada por el usuario.")
                return # Salir limpiamente
            else:
                print("Continuando con la adición de datos...")

        print("Iniciando transacción para carga de datos...")
        # Usar 'with conn:' para manejo automático de transacción
        with conn:
            # 3. Crear Usuarios
            usuarios, admin_user_id = crear_usuarios(conn, cursor)
            if not usuarios:
                 raise Exception("Fallo crítico: No hay usuarios disponibles después de crear/verificar. Abortando.")
            if admin_user_id is None:
                # Intentar obtener admin ID de nuevo o asignar fallback
                admin_user_id = next((u['id'] for u in usuarios if u['rol'] == 'administrador'), None)
                if not admin_user_id and usuarios:
                    admin_user_id = usuarios[0]['id']
                    print(f"WARN: No se encontró admin. Usando ID {admin_user_id} para logs.")
                elif not admin_user_id:
                     raise Exception("No se pudo determinar un ID de usuario para realizar logs. Abortando.")
            print("-" * 30)

            # 4. Crear Pacientes
            pacientes, log_user_id = crear_pacientes(conn, cursor, NUM_PACIENTES, usuarios, admin_user_id)
            if not pacientes and NUM_PACIENTES > 0:
                 print("WARN: No se crearon nuevos pacientes.")
                 # Decidir si continuar o no. Por ahora continuamos.
            print("-" * 30)

            # 5. Crear Consultas y Detalles para cada Paciente
            # Usar el ID que se usó para loguear la creación de pacientes
            if pacientes: # Solo si se crearon pacientes
                 crear_consultas_y_detalles(conn, cursor, pacientes, usuarios, log_user_id)
            print("-" * 30)
            
            # Commit es automático al salir de 'with conn:' si no hubo excepciones

        print("Datos cargados exitosamente!") # Mensaje si todo fue bien

    except Exception as e:
        print(f"\n!!! ERROR DURANTE LA CARGA DE DATOS: {e} !!!")
        # Rollback es automático con 'with conn:' si la excepción ocurrió dentro del bloque
        print("La transacción debería haber sido revertida automáticamente (ROLLBACK).")
        traceback.print_exc()

    finally:
        if conn:
            conn.close()
            print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    print("--- carga_datos.py: Entering __main__ block ---")
    main()
    print("--- carga_datos.py: main() finished ---")