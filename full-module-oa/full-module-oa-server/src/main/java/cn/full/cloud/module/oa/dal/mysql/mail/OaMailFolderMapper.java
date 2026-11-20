package cn.full.cloud.module.oa.dal.mysql.mail;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.oa.dal.dataobject.mail.OaMailFolderDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * 企业邮箱文件夹 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface OaMailFolderMapper extends BaseMapperX<OaMailFolderDO> {

    default List<OaMailFolderDO> selectListByAccountId(Long accountId) {
        return selectList(new LambdaQueryWrapperX<OaMailFolderDO>()
                .eq(OaMailFolderDO::getAccountId, accountId).orderByAsc(OaMailFolderDO::getId));
    }

}
