FROM eclipse-temurin:25-jre

ARG JAR_FILE
ARG APP_PORT

WORKDIR /app
COPY ${JAR_FILE} app.jar

# 小内存默认值；compose 会按服务通过 JAVA_OPTS 覆盖
ENV TZ=Asia/Shanghai \
    JAVA_OPTS="-Xms192m -Xmx320m -XX:MaxMetaspaceSize=192m -XX:ReservedCodeCacheSize=64m -XX:MaxDirectMemorySize=96m -Xss512k -XX:ActiveProcessorCount=2 -XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError"
EXPOSE ${APP_PORT}

CMD java ${JAVA_OPTS} -Djava.security.egd=file:/dev/./urandom -jar app.jar
