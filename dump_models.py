# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AccountsAttribute(models.Model):
    id = models.BigAutoField(primary_key=True)
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=255)
    aplicacao = models.ForeignKey('Tblaplicacao', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey('AuthUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'accounts_attribute'
        unique_together = (('user', 'aplicacao', 'key'),)


class AccountsRole(models.Model):
    id = models.BigAutoField(primary_key=True)
    nomeperfil = models.CharField(max_length=100)
    codigoperfil = models.CharField(max_length=100)
    aplicacao = models.ForeignKey('Tblaplicacao', models.DO_NOTHING, blank=True, null=True)
    group = models.ForeignKey('AuthGroup', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'accounts_role'
        unique_together = (('aplicacao', 'codigoperfil'),)


class AccountsSession(models.Model):
    id = models.BigAutoField(primary_key=True)
    jti = models.CharField(unique=True, max_length=255)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked = models.BooleanField()
    revoked_at = models.DateTimeField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField()
    user = models.ForeignKey('AuthUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'accounts_session'


class AccountsUserrole(models.Model):
    id = models.BigAutoField(primary_key=True)
    aplicacao = models.ForeignKey('Tblaplicacao', models.DO_NOTHING, blank=True, null=True)
    role = models.ForeignKey(AccountsRole, models.DO_NOTHING)
    user = models.ForeignKey('AuthUser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'accounts_userrole'
        unique_together = (('user', 'aplicacao', 'role'),)


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class AuthtokenToken(models.Model):
    key = models.CharField(primary_key=True, max_length=40)
    created = models.DateTimeField()
    user = models.OneToOneField(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'authtoken_token'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class Tblacaoanotacaoalinhamento(models.Model):
    idacaoanotacaoalinhamento = models.AutoField(primary_key=True)
    datdataanotacaoalinhamento = models.DateTimeField()
    strdescricaoanotacaoalinhamento = models.CharField(max_length=500)
    strlinkanotacaoalinhamento = models.CharField(max_length=500, blank=True, null=True)
    strnumeromonitoramento = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    idacao = models.ForeignKey('Tblacoes', models.DO_NOTHING, db_column='idacao')
    idtipoanotacaoalinhamento = models.ForeignKey('Tbltipoanotacaoalinhamento', models.DO_NOTHING, db_column='idtipoanotacaoalinhamento')

    class Meta:
        managed = False
        db_table = 'tblacaoanotacaoalinhamento'
        unique_together = (('idacao', 'idtipoanotacaoalinhamento', 'datdataanotacaoalinhamento'),)


class Tblacaodestaque(models.Model):
    idacaodestaque = models.AutoField(primary_key=True)
    datdatadestaque = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    idacao = models.ForeignKey('Tblacoes', models.DO_NOTHING, db_column='idacao')

    class Meta:
        managed = False
        db_table = 'tblacaodestaque'
        unique_together = (('idacao', 'datdatadestaque'),)


class Tblacaoprazo(models.Model):
    idacaoprazo = models.AutoField(primary_key=True)
    isacaoprazoativo = models.BooleanField()
    strprazo = models.CharField(max_length=20)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    idacao = models.ForeignKey('Tblacoes', models.DO_NOTHING, db_column='idacao')

    class Meta:
        managed = False
        db_table = 'tblacaoprazo'
        unique_together = (('idacao', 'isacaoprazoativo'),)


class Tblacoes(models.Model):
    idacao = models.AutoField(primary_key=True)
    strapelido = models.CharField(max_length=50)
    strdescricaoacao = models.CharField(max_length=350)
    strdescricaoentrega = models.CharField(max_length=20)
    datdataentrega = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    idtipoentravealerta = models.ForeignKey('Tbltipoentravealerta', models.DO_NOTHING, db_column='idtipoentravealerta', blank=True, null=True)
    idvigenciapngi = models.ForeignKey('Tblvigenciapngi', models.DO_NOTHING, db_column='idvigenciapngi')

    class Meta:
        managed = False
        db_table = 'tblacoes'


class Tblaplicacao(models.Model):
    idaplicacao = models.AutoField(primary_key=True)
    codigointerno = models.CharField(unique=True, max_length=50)
    nomeaplicacao = models.CharField(max_length=200)
    base_url = models.CharField(max_length=200, blank=True, null=True)
    isshowinportal = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'tblaplicacao'


class Tblcargapatriarca(models.Model):
    idcargapatriarca = models.BigAutoField(primary_key=True)
    strmensagemretorno = models.TextField(blank=True, null=True)
    datdatahorainicio = models.DateTimeField()
    datdatahorafim = models.DateTimeField(blank=True, null=True)
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')
    idstatuscarga = models.ForeignKey('Tblstatuscarga', models.DO_NOTHING, db_column='idstatuscarga')
    idtipocarga = models.ForeignKey('Tbltipocarga', models.DO_NOTHING, db_column='idtipocarga')
    idtokenenviocarga = models.ForeignKey('Tbltokenenviocarga', models.DO_NOTHING, db_column='idtokenenviocarga')

    class Meta:
        managed = False
        db_table = 'tblcargapatriarca'


class Tblclassificacaousuario(models.Model):
    idclassificacaousuario = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tblclassificacaousuario'


class Tbldetalhestatuscarga(models.Model):
    iddetalhestatuscarga = models.BigAutoField(primary_key=True)
    datregistro = models.DateTimeField()
    strmensagem = models.TextField(blank=True, null=True)
    idcargapatriarca = models.ForeignKey(Tblcargapatriarca, models.DO_NOTHING, db_column='idcargapatriarca')
    idstatuscarga = models.ForeignKey('Tblstatuscarga', models.DO_NOTHING, db_column='idstatuscarga')

    class Meta:
        managed = False
        db_table = 'tbldetalhestatuscarga'


class Tbleixos(models.Model):
    ideixo = models.AutoField(primary_key=True)
    strdescricaoeixo = models.CharField(max_length=100)
    stralias = models.CharField(unique=True, max_length=5)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tbleixos'


class Tbllotacao(models.Model):
    idlotacao = models.BigAutoField(primary_key=True)
    strcpf = models.CharField(max_length=14)
    strcargooriginal = models.CharField(max_length=255, blank=True, null=True)
    strcargonormalizado = models.CharField(max_length=255, blank=True, null=True)
    flgvalido = models.BooleanField()
    strerrosvalidacao = models.TextField(blank=True, null=True)
    datreferencia = models.DateField(blank=True, null=True)
    datcriacao = models.DateTimeField()
    datalteracao = models.DateTimeField(blank=True, null=True)
    idusuarioalteracao = models.IntegerField(blank=True, null=True)
    idusuariocriacao = models.IntegerField(blank=True, null=True)
    idlotacaoversao = models.ForeignKey('Tbllotacaoversao', models.DO_NOTHING, db_column='idlotacaoversao')
    idorganogramaversao = models.ForeignKey('Tblorganogramaversao', models.DO_NOTHING, db_column='idorganogramaversao')
    idorgaolotacao = models.ForeignKey('Tblorgaounidade', models.DO_NOTHING, db_column='idorgaolotacao')
    idunidadelotacao = models.ForeignKey('Tblorgaounidade', models.DO_NOTHING, db_column='idunidadelotacao', related_name='tbllotacao_idunidadelotacao_set', blank=True, null=True)
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')

    class Meta:
        managed = False
        db_table = 'tbllotacao'


class Tbllotacaoinconsistencia(models.Model):
    idinconsistencia = models.BigAutoField(primary_key=True)
    strtipo = models.CharField(max_length=100)
    strdetalhe = models.TextField()
    datregistro = models.DateTimeField()
    idlotacao = models.ForeignKey(Tbllotacao, models.DO_NOTHING, db_column='idlotacao')

    class Meta:
        managed = False
        db_table = 'tbllotacaoinconsistencia'


class Tbllotacaojsonorgao(models.Model):
    idlotacaojsonorgao = models.BigAutoField(primary_key=True)
    jsconteudo = models.JSONField()
    datcriacao = models.DateTimeField()
    datenvioapi = models.DateTimeField(blank=True, null=True)
    strstatusenvio = models.CharField(max_length=30, blank=True, null=True)
    strmensagemretorno = models.TextField(blank=True, null=True)
    idlotacaoversao = models.ForeignKey('Tbllotacaoversao', models.DO_NOTHING, db_column='idlotacaoversao')
    idorganogramaversao = models.ForeignKey('Tblorganogramaversao', models.DO_NOTHING, db_column='idorganogramaversao')
    idorgaolotacao = models.ForeignKey('Tblorgaounidade', models.DO_NOTHING, db_column='idorgaolotacao')
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')

    class Meta:
        managed = False
        db_table = 'tbllotacaojsonorgao'


class Tbllotacaoversao(models.Model):
    idlotacaoversao = models.BigAutoField(primary_key=True)
    strorigem = models.CharField(max_length=50)
    strtipoarquivooriginal = models.CharField(max_length=20, blank=True, null=True)
    strnomearquivooriginal = models.CharField(max_length=255, blank=True, null=True)
    datprocessamento = models.DateTimeField()
    strstatusprocessamento = models.CharField(max_length=30)
    strmensagemprocessamento = models.TextField(blank=True, null=True)
    flgativo = models.BooleanField()
    idorganogramaversao = models.ForeignKey('Tblorganogramaversao', models.DO_NOTHING, db_column='idorganogramaversao')
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')

    class Meta:
        managed = False
        db_table = 'tbllotacaoversao'


class Tblorganogramajson(models.Model):
    idorganogramajson = models.BigAutoField(primary_key=True)
    jsconteudo = models.JSONField()
    datcriacao = models.DateTimeField()
    datenvioapi = models.DateTimeField(blank=True, null=True)
    strstatusenvio = models.CharField(max_length=30, blank=True, null=True)
    strmensagemretorno = models.TextField(blank=True, null=True)
    idorganogramaversao = models.OneToOneField('Tblorganogramaversao', models.DO_NOTHING, db_column='idorganogramaversao')

    class Meta:
        managed = False
        db_table = 'tblorganogramajson'


class Tblorganogramaversao(models.Model):
    idorganogramaversao = models.BigAutoField(primary_key=True)
    strorigem = models.CharField(max_length=50)
    strtipoarquivooriginal = models.CharField(max_length=20, blank=True, null=True)
    strnomearquivooriginal = models.CharField(max_length=255, blank=True, null=True)
    datprocessamento = models.DateTimeField()
    strstatusprocessamento = models.CharField(max_length=30)
    strmensagemprocessamento = models.TextField(blank=True, null=True)
    flgativo = models.BooleanField()
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')

    class Meta:
        managed = False
        db_table = 'tblorganogramaversao'


class Tblorgaounidade(models.Model):
    idorgaounidade = models.BigAutoField(primary_key=True)
    strnome = models.CharField(max_length=255)
    strsigla = models.CharField(max_length=50)
    strnumerohierarquia = models.CharField(max_length=50, blank=True, null=True)
    intnivelhierarquia = models.IntegerField(blank=True, null=True)
    flgativo = models.BooleanField()
    datcriacao = models.DateTimeField()
    datalteracao = models.DateTimeField(blank=True, null=True)
    idorganogramaversao = models.ForeignKey(Tblorganogramaversao, models.DO_NOTHING, db_column='idorganogramaversao')
    idorgaounidadepai = models.ForeignKey('self', models.DO_NOTHING, db_column='idorgaounidadepai', blank=True, null=True)
    idusuarioalteracao = models.IntegerField(blank=True, null=True)
    idusuariocriacao = models.IntegerField(blank=True, null=True)
    idpatriarca = models.ForeignKey('Tblpatriarca', models.DO_NOTHING, db_column='idpatriarca')

    class Meta:
        managed = False
        db_table = 'tblorgaounidade'


class Tblpatriarca(models.Model):
    idpatriarca = models.BigAutoField(primary_key=True)
    idexternopatriarca = models.UUIDField(unique=True)
    strsiglapatriarca = models.CharField(max_length=20)
    strnome = models.CharField(max_length=255)
    datcriacao = models.DateTimeField()
    datalteracao = models.DateTimeField(blank=True, null=True)
    idusuarioalteracao = models.IntegerField(blank=True, null=True)
    idusuariocriacao = models.IntegerField()
    idstatusprogresso = models.ForeignKey('Tblstatusprogresso', models.DO_NOTHING, db_column='idstatusprogresso')

    class Meta:
        managed = False
        db_table = 'tblpatriarca'


class Tblrelacaoacaousuarioresponsavel(models.Model):
    idacaousuarioresponsavel = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    idacao = models.ForeignKey(Tblacoes, models.DO_NOTHING, db_column='idacao')
    idusuarioresponsavel = models.ForeignKey('Tblusuarioresponsavel', models.DO_NOTHING, db_column='idusuarioresponsavel')

    class Meta:
        managed = False
        db_table = 'tblrelacaoacaousuarioresponsavel'
        unique_together = (('idacao', 'idusuarioresponsavel'),)


class Tblsituacaoacao(models.Model):
    idsituacaoacao = models.AutoField(primary_key=True)
    strdescricaosituacao = models.CharField(unique=True, max_length=15)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tblsituacaoacao'


class Tblstatuscarga(models.Model):
    idstatuscarga = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=150)
    flgsucesso = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'tblstatuscarga'


class Tblstatusprogresso(models.Model):
    idstatusprogresso = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tblstatusprogresso'


class Tblstatustokenenviocarga(models.Model):
    idstatustokenenviocarga = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tblstatustokenenviocarga'


class Tblstatususuario(models.Model):
    idstatususuario = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tblstatususuario'


class Tbltipoanotacaoalinhamento(models.Model):
    idtipoanotacaoalinhamento = models.AutoField(primary_key=True)
    strdescricaotipoanotacaoalinhamento = models.CharField(max_length=50)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tbltipoanotacaoalinhamento'


class Tbltipocarga(models.Model):
    idtipocarga = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tbltipocarga'


class Tbltipoentravealerta(models.Model):
    idtipoentravealerta = models.AutoField(primary_key=True)
    strdescricaotipoentravealerta = models.CharField(max_length=20)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tbltipoentravealerta'


class Tbltipousuario(models.Model):
    idtipousuario = models.SmallIntegerField(primary_key=True)
    strdescricao = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tbltipousuario'


class Tbltokenenviocarga(models.Model):
    idtokenenviocarga = models.BigAutoField(primary_key=True)
    strtokenretorno = models.CharField(max_length=1000)
    datdatahorainicio = models.DateTimeField()
    datdatahorafim = models.DateTimeField(blank=True, null=True)
    idpatriarca = models.ForeignKey(Tblpatriarca, models.DO_NOTHING, db_column='idpatriarca')
    idstatustokenenviocarga = models.ForeignKey(Tblstatustokenenviocarga, models.DO_NOTHING, db_column='idstatustokenenviocarga')

    class Meta:
        managed = False
        db_table = 'tbltokenenviocarga'


class Tblusuario(models.Model):
    user = models.OneToOneField(AuthUser, models.DO_NOTHING, primary_key=True)
    strnome = models.CharField(max_length=200)
    orgao = models.CharField(max_length=100, blank=True, null=True)
    datacriacao = models.DateTimeField()
    data_alteracao = models.DateTimeField(blank=True, null=True)
    idclassificacaousuario = models.ForeignKey(Tblclassificacaousuario, models.DO_NOTHING, db_column='idclassificacaousuario')
    idusuarioalteracao = models.ForeignKey(AuthUser, models.DO_NOTHING, db_column='idusuarioalteracao', related_name='tblusuario_idusuarioalteracao_set', blank=True, null=True)
    idusuariocriacao = models.ForeignKey(AuthUser, models.DO_NOTHING, db_column='idusuariocriacao', related_name='tblusuario_idusuariocriacao_set', blank=True, null=True)
    idstatususuario = models.ForeignKey(Tblstatususuario, models.DO_NOTHING, db_column='idstatususuario')
    idtipousuario = models.ForeignKey(Tbltipousuario, models.DO_NOTHING, db_column='idtipousuario')

    class Meta:
        managed = False
        db_table = 'tblusuario'


class Tblusuarioresponsavel(models.Model):
    idusuario = models.IntegerField(primary_key=True)
    strtelefone = models.CharField(max_length=20)
    strorgao = models.CharField(max_length=20)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tblusuarioresponsavel'


class Tblvigenciapngi(models.Model):
    idvigenciapngi = models.AutoField(primary_key=True)
    strdescricaovigenciapngi = models.CharField(max_length=100)
    datiniciovigencia = models.DateField()
    datfinalvigencia = models.DateField()
    isvigenciaativa = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'tblvigenciapngi'


class TokenBlacklistBlacklistedtoken(models.Model):
    id = models.BigAutoField(primary_key=True)
    blacklisted_at = models.DateTimeField()
    token = models.OneToOneField('TokenBlacklistOutstandingtoken', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'token_blacklist_blacklistedtoken'


class TokenBlacklistOutstandingtoken(models.Model):
    id = models.BigAutoField(primary_key=True)
    token = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField()
    user = models.ForeignKey(AuthUser, models.DO_NOTHING, blank=True, null=True)
    jti = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'token_blacklist_outstandingtoken'
